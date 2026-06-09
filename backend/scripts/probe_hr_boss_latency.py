"""Probe HR Boss agent SSE latency against a running Gateway.

Example:
    uv run python scripts/probe_hr_boss_latency.py \
        --base-url http://127.0.0.1:8001 \
        --email admin@example.com \
        --password 'your-password'
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, asdict
from typing import Any
from uuid import uuid4


DEFAULT_QUESTIONS = (
    "我需要一个研发经理，帮从集团推荐一个瓷粉研发的人",
    "福建火炬电子科技股份有限公司有多少员工？",
)


@dataclass
class ProbeResult:
    question: str
    thread_id: str
    status: str
    headers_ms: int | None
    first_byte_ms: int | None
    total_ms: int
    sse_frames: int
    bytes_read: int
    events: dict[str, int]
    error: str | None = None


class GatewayClient:
    def __init__(self, base_url: str, *, raw_cookie: str | None = None) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.raw_cookie = raw_cookie

    def _url(self, path: str) -> str:
        return urllib.parse.urljoin(self.base_url, path.lstrip("/"))

    def _csrf_token(self) -> str | None:
        if self.raw_cookie:
            for part in self.raw_cookie.split(";"):
                name, _, value = part.strip().partition("=")
                if name == "csrf_token" and value:
                    return value
        for cookie in self.cookie_jar:
            if cookie.name == "csrf_token":
                return cookie.value
        return None

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
        headers: dict[str, str] = {}
        data: bytes | None = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        csrf = self._csrf_token()
        if csrf:
            headers["X-CSRF-Token"] = csrf
        if self.raw_cookie:
            headers["Cookie"] = self.raw_cookie

        req = urllib.request.Request(self._url(path), data=data, headers=headers, method=method)
        return self.opener.open(req, timeout=timeout)

    def login(self, email: str, password: str, *, timeout: float = 30.0) -> None:
        with self.request(
            "POST",
            "/api/v1/auth/login/local",
            form={"username": email, "password": password},
            timeout=timeout,
        ) as resp:
            resp.read()

    def ensure_thread(self, thread_id: str, *, assistant_id: str, agent_name: str, timeout: float = 30.0) -> None:
        try:
            with self.request(
                "POST",
                "/api/threads",
                payload={
                    "thread_id": thread_id,
                    "assistant_id": assistant_id,
                    "metadata": {"agent_name": agent_name},
                },
                timeout=timeout,
            ) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return
            raise


def _decode_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    return f"HTTP {exc.code}: {body[:500]}"


def probe_question(
    client: GatewayClient,
    *,
    thread_id: str,
    assistant_id: str,
    agent_name: str,
    question: str,
    stream_mode: list[str] | None,
    include_values_stream: bool,
    timeout: float,
) -> ProbeResult:
    payload: dict[str, Any] = {
        "assistant_id": assistant_id,
        "input": {"messages": [{"role": "user", "content": question}]},
        "context": {"agent_name": agent_name},
        "stream_subgraphs": True,
        "on_disconnect": "cancel",
    }
    if stream_mode:
        payload["stream_mode"] = stream_mode
    if include_values_stream:
        payload["context"]["include_values_stream"] = True

    started = time.perf_counter()
    headers_at: float | None = None
    first_byte_at: float | None = None
    bytes_read = 0
    frames = 0
    current_event: str | None = None
    events: Counter[str] = Counter()

    try:
        with client.request(
            "POST",
            f"/api/threads/{urllib.parse.quote(thread_id)}/runs/stream",
            payload=payload,
            timeout=timeout,
        ) as resp:
            headers_at = time.perf_counter()
            while True:
                line = resp.readline()
                now = time.perf_counter()
                if not line:
                    break
                if first_byte_at is None:
                    first_byte_at = now
                bytes_read += len(line)
                if line.startswith(b"event: "):
                    current_event = line[len(b"event: ") :].strip().decode("utf-8", errors="replace")
                    continue
                if line in (b"\n", b"\r\n"):
                    frames += 1
                    if current_event:
                        events[current_event] += 1
                        if current_event == "end":
                            break
                    current_event = None
        status = "ok" if events.get("end") else "closed"
        error = None
    except urllib.error.HTTPError as exc:
        status = "http_error"
        error = _decode_http_error(exc)
    except Exception as exc:
        status = "error"
        error = str(exc)

    finished = time.perf_counter()
    return ProbeResult(
        question=question,
        thread_id=thread_id,
        status=status,
        headers_ms=int((headers_at - started) * 1000) if headers_at is not None else None,
        first_byte_ms=int((first_byte_at - started) * 1000) if first_byte_at is not None else None,
        total_ms=int((finished - started) * 1000),
        sse_frames=frames,
        bytes_read=bytes_read,
        events=dict(events),
        error=error,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("DEER_FLOW_BASE_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--email", default=os.getenv("DEER_FLOW_EMAIL"))
    parser.add_argument("--password", default=os.getenv("DEER_FLOW_PASSWORD"))
    parser.add_argument("--cookie", default=os.getenv("DEER_FLOW_COOKIE"), help="Raw Cookie header, e.g. access_token=...; csrf_token=...")
    parser.add_argument("--thread-id", default=os.getenv("DEER_FLOW_THREAD_ID") or f"probe-{uuid4()}")
    parser.add_argument("--assistant-id", default="lead_agent")
    parser.add_argument("--agent-name", default="hr-boss-agent")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--question", action="append", dest="questions")
    parser.add_argument("--stream-mode", action="append", dest="stream_modes", help="Repeat for multiple modes, e.g. --stream-mode values --stream-mode messages-tuple")
    parser.add_argument("--include-values-stream", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    questions = args.questions or list(DEFAULT_QUESTIONS)
    client = GatewayClient(args.base_url, raw_cookie=args.cookie)

    if args.email and args.password and not args.cookie:
        client.login(args.email, args.password, timeout=args.timeout)

    client.ensure_thread(
        args.thread_id,
        assistant_id=args.assistant_id,
        agent_name=args.agent_name,
        timeout=args.timeout,
    )

    results = [
        probe_question(
            client,
            thread_id=args.thread_id,
            assistant_id=args.assistant_id,
            agent_name=args.agent_name,
            question=question,
            stream_mode=args.stream_modes,
            include_values_stream=args.include_values_stream,
            timeout=args.timeout,
        )
        for question in questions
    ]

    if args.as_json:
        print(json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2))
    else:
        print(f"thread_id: {args.thread_id}")
        for index, result in enumerate(results, start=1):
            print(f"\n[{index}] {result.question}")
            print(
                "status={status} headers={headers}ms first_byte={first}ms total={total}ms frames={frames} bytes={bytes} events={events}".format(
                    status=result.status,
                    headers=result.headers_ms,
                    first=result.first_byte_ms,
                    total=result.total_ms,
                    frames=result.sse_frames,
                    bytes=result.bytes_read,
                    events=result.events,
                )
            )
            if result.error:
                print(f"error={result.error}")
    return 0 if all(result.status in {"ok", "closed"} for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
