from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from app.channels.base import Channel
from app.channels.message_bus import (
    InboundMessageType,
    MessageBus,
    OutboundMessage,
    ResolvedAttachment,
)

logger = logging.getLogger(__name__)

_WECOM_FEEDBACK_REASON_LABELS = {
    1: "与问题无关",
    2: "内容不完整",
    3: "内容有错误",
    4: "数据分析错误",
}


class WeComChannel(Channel):
    def __init__(self, bus: MessageBus, config: dict[str, Any]) -> None:
        super().__init__(name="wecom", bus=bus, config=config)
        self._bot_id: str | None = None
        self._bot_secret: str | None = None
        self._ws_client = None
        self._ws_task: asyncio.Task | None = None
        self._ws_frames: dict[str, dict[str, Any]] = {}
        self._ws_stream_ids: dict[str, str] = {}
        self._ws_stream_timeout_tasks: dict[str, asyncio.Task[None]] = {}
        self._detached_streams: set[str] = set()
        self._working_message = "Working on it..."
        timeout = config.get("stream_soft_timeout_seconds", 0)
        self._stream_soft_timeout_seconds = float(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else 0.0
        timeout_message = config.get("stream_timeout_message")
        self._stream_timeout_message = (
            timeout_message
            if isinstance(timeout_message, str) and timeout_message
            else "This task is taking longer than expected. The final result will be sent separately."
        )
        self._feedback_repo = config.get("feedback_repo")

    @property
    def supports_streaming(self) -> bool:
        return True

    def _clear_ws_context(self, thread_ts: str | None) -> None:
        if not thread_ts:
            return
        timeout_task = self._ws_stream_timeout_tasks.pop(thread_ts, None)
        if timeout_task is not None and timeout_task is not asyncio.current_task():
            timeout_task.cancel()
        self._ws_frames.pop(thread_ts, None)
        self._ws_stream_ids.pop(thread_ts, None)
        self._detached_streams.discard(thread_ts)

    def _detach_ws_stream(self, thread_ts: str | None) -> None:
        if not thread_ts:
            return
        timeout_task = self._ws_stream_timeout_tasks.pop(thread_ts, None)
        if timeout_task is not None and timeout_task is not asyncio.current_task():
            timeout_task.cancel()
        self._ws_frames.pop(thread_ts, None)
        self._ws_stream_ids.pop(thread_ts, None)
        self._detached_streams.add(thread_ts)

    def _schedule_ws_stream_timeout(self, thread_ts: str) -> None:
        if self._stream_soft_timeout_seconds <= 0:
            return
        previous = self._ws_stream_timeout_tasks.pop(thread_ts, None)
        if previous is not None:
            previous.cancel()
        self._ws_stream_timeout_tasks[thread_ts] = asyncio.create_task(self._finish_ws_stream_after_timeout(thread_ts))

    async def _finish_ws_stream_after_timeout(self, thread_ts: str) -> None:
        try:
            await asyncio.sleep(self._stream_soft_timeout_seconds)
            frame = self._ws_frames.get(thread_ts)
            stream_id = self._ws_stream_ids.get(thread_ts)
            if not self._ws_client or not frame or not stream_id:
                return

            self._detach_ws_stream(thread_ts)
            try:
                await self._ws_client.reply_stream(frame, stream_id, self._stream_timeout_message, True)
            except Exception:
                logger.warning("[WeCom] failed to finish stream at soft timeout: msg_id=%s", thread_ts, exc_info=True)
        except asyncio.CancelledError:
            return
        finally:
            current = self._ws_stream_timeout_tasks.get(thread_ts)
            if current is asyncio.current_task():
                self._ws_stream_timeout_tasks.pop(thread_ts, None)

    def _get_feedback_repo(self):
        if self._feedback_repo is not None:
            return self._feedback_repo
        try:
            from deerflow.persistence.engine import get_session_factory
            from deerflow.persistence.feedback import FeedbackRepository
        except Exception:
            return None
        session_factory = get_session_factory()
        if session_factory is None:
            return None
        self._feedback_repo = FeedbackRepository(session_factory)
        return self._feedback_repo

    async def _send_ws_upload_command(self, req_id: str, body: dict[str, Any], cmd: str) -> dict[str, Any]:
        if not self._ws_client:
            raise RuntimeError("WeCom WebSocket client is not available")

        ws_manager = getattr(self._ws_client, "_ws_manager", None)
        send_reply = getattr(ws_manager, "send_reply", None)
        if not callable(send_reply):
            raise RuntimeError("Installed wecom-aibot-python-sdk does not expose the WebSocket media upload API expected by DeerFlow. Use wecom-aibot-python-sdk==0.1.6 or update the adapter.")

        send_reply_async = cast(Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]], send_reply)
        return await send_reply_async(req_id, body, cmd)

    async def start(self) -> None:
        if self._running:
            return

        bot_id = self.config.get("bot_id")
        bot_secret = self.config.get("bot_secret")
        working_message = self.config.get("working_message")

        self._bot_id = bot_id if isinstance(bot_id, str) and bot_id else None
        self._bot_secret = bot_secret if isinstance(bot_secret, str) and bot_secret else None
        self._working_message = working_message if isinstance(working_message, str) and working_message else "Working on it..."

        if not self._bot_id or not self._bot_secret:
            logger.error("WeCom channel requires bot_id and bot_secret")
            return

        try:
            from aibot import WSClient, WSClientOptions
        except ImportError:
            logger.error("wecom-aibot-python-sdk is not installed. Install it with: uv add wecom-aibot-python-sdk")
            return
        else:
            self._ws_client = WSClient(WSClientOptions(bot_id=self._bot_id, secret=self._bot_secret, logger=logger))
            self._ws_client.on("message.text", self._on_ws_text)
            self._ws_client.on("message.mixed", self._on_ws_mixed)
            self._ws_client.on("message.image", self._on_ws_image)
            self._ws_client.on("message.file", self._on_ws_file)
            self._ws_client.on("event", self._on_ws_event)
            self._ws_client.on("event.feedback_event", self._on_ws_feedback_event)
            self._ws_task = asyncio.create_task(self._ws_client.connect())

            self._running = True
            self.bus.subscribe_outbound(self._on_outbound)
        logger.info("WeCom channel started")

    async def stop(self) -> None:
        self._running = False
        self.bus.unsubscribe_outbound(self._on_outbound)
        if self._ws_task:
            try:
                self._ws_task.cancel()
            except Exception:
                pass
            self._ws_task = None
        if self._ws_client:
            try:
                self._ws_client.disconnect()
            except Exception:
                pass
        self._ws_client = None
        for timeout_task in self._ws_stream_timeout_tasks.values():
            timeout_task.cancel()
        self._ws_stream_timeout_tasks.clear()
        self._ws_frames.clear()
        self._ws_stream_ids.clear()
        self._detached_streams.clear()
        logger.info("WeCom channel stopped")

    async def send(self, msg: OutboundMessage, *, _max_retries: int = 3) -> None:
        if self._ws_client:
            await self._send_ws(msg, _max_retries=_max_retries)
            return
        logger.warning("[WeCom] send called but WebSocket client is not available")

    async def _on_outbound(self, msg: OutboundMessage) -> None:
        if msg.channel_name != self.name:
            return

        try:
            await self.send(msg)
        except Exception:
            logger.exception("Failed to send outbound message on channel %s", self.name)
            if msg.is_final:
                self._clear_ws_context(msg.thread_ts)
            return

        for attachment in msg.attachments:
            try:
                success = await self.send_file(msg, attachment)
                if not success:
                    logger.warning("[%s] file upload skipped for %s", self.name, attachment.filename)
            except Exception:
                logger.exception("[%s] failed to upload file %s", self.name, attachment.filename)

        if msg.is_final:
            self._clear_ws_context(msg.thread_ts)

    async def send_file(self, msg: OutboundMessage, attachment: ResolvedAttachment) -> bool:
        if not msg.is_final:
            return True
        if not self._ws_client:
            return False
        if not msg.thread_ts:
            return False
        frame = self._ws_frames.get(msg.thread_ts)
        if not frame:
            return False

        media_type = "image" if attachment.is_image else "file"
        size_limit = 2 * 1024 * 1024 if attachment.is_image else 20 * 1024 * 1024
        if attachment.size > size_limit:
            logger.warning(
                "[WeCom] %s too large (%d bytes), skipping: %s",
                media_type,
                attachment.size,
                attachment.filename,
            )
            return False

        try:
            media_id = await self._upload_media_ws(
                media_type=media_type,
                filename=attachment.filename,
                path=str(attachment.actual_path),
                size=attachment.size,
            )
            if not media_id:
                return False

            body = {media_type: {"media_id": media_id}, "msgtype": media_type}
            await self._ws_client.reply(frame, body)
            logger.debug("[WeCom] %s sent via ws: %s", media_type, attachment.filename)
            return True
        except Exception:
            logger.exception("[WeCom] failed to upload/send file via ws: %s", attachment.filename)
            return False

    async def _on_ws_text(self, frame: dict[str, Any]) -> None:
        body = frame.get("body", {}) or {}
        text = ((body.get("text") or {}).get("content") or "").strip()
        quote = body.get("quote", {}).get("text", {}).get("content", "").strip()
        if not text and not quote:
            return
        await self._publish_ws_inbound(frame, text + (f"\nQuote message: {quote}" if quote else ""))

    async def _on_ws_mixed(self, frame: dict[str, Any]) -> None:
        body = frame.get("body", {}) or {}
        mixed = body.get("mixed") or {}
        items = mixed.get("msg_item") or []
        parts: list[str] = []
        files: list[dict[str, Any]] = []
        for item in items:
            item_type = (item or {}).get("msgtype")
            if item_type == "text":
                content = (((item or {}).get("text") or {}).get("content") or "").strip()
                if content:
                    parts.append(content)
            elif item_type in ("image", "file"):
                payload = (item or {}).get(item_type) or {}
                url = payload.get("url")
                aeskey = payload.get("aeskey")
                if isinstance(url, str) and url:
                    files.append(
                        {
                            "type": item_type,
                            "url": url,
                            "aeskey": (aeskey if isinstance(aeskey, str) and aeskey else None),
                        }
                    )
        text = "\n\n".join(parts).strip()
        if not text and not files:
            return
        if not text:
            text = "（receive image/file）"
        await self._publish_ws_inbound(frame, text, files=files)

    async def _on_ws_image(self, frame: dict[str, Any]) -> None:
        body = frame.get("body", {}) or {}
        image = body.get("image") or {}
        url = image.get("url")
        aeskey = image.get("aeskey")
        if not isinstance(url, str) or not url:
            return
        await self._publish_ws_inbound(
            frame,
            "（receive image ）",
            files=[
                {
                    "type": "image",
                    "url": url,
                    "aeskey": aeskey if isinstance(aeskey, str) and aeskey else None,
                }
            ],
        )

    async def _on_ws_file(self, frame: dict[str, Any]) -> None:
        body = frame.get("body", {}) or {}
        file_obj = body.get("file") or {}
        url = file_obj.get("url")
        aeskey = file_obj.get("aeskey")
        if not isinstance(url, str) or not url:
            return
        await self._publish_ws_inbound(
            frame,
            "（receive file）",
            files=[
                {
                    "type": "file",
                    "url": url,
                    "aeskey": aeskey if isinstance(aeskey, str) and aeskey else None,
                }
            ],
        )

    async def _on_ws_event(self, frame: dict[str, Any]) -> None:
        body = frame.get("body", {}) or {}
        event = body.get("event") if isinstance(body.get("event"), dict) else {}
        from_user = body.get("from") if isinstance(body.get("from"), dict) else {}
        logger.info(
            "[WeCom] event received: event_type=%s user_id=%s chat_id=%s chat_type=%s msg_id=%s aibot_id=%s",
            event.get("eventtype"),
            from_user.get("userid"),
            body.get("chatid"),
            body.get("chattype"),
            body.get("msgid"),
            body.get("aibotid"),
        )

    async def _on_ws_feedback_event(self, frame: dict[str, Any]) -> None:
        body = frame.get("body", {}) or {}
        event = body.get("event") if isinstance(body.get("event"), dict) else {}
        feedback_event = event.get("feedback_event") if isinstance(event.get("feedback_event"), dict) else {}
        from_user = body.get("from") if isinstance(body.get("from"), dict) else {}
        native_feedback_id = feedback_event.get("id")
        feedback_type = feedback_event.get("type")
        content = feedback_event.get("content")
        reasons = feedback_event.get("inaccurate_reason_list")
        user_id = from_user.get("userid")
        logger.info(
            "[WeCom] feedback_event received: feedback_id=%s type=%s content=%s reasons=%s user_id=%s chat_id=%s chat_type=%s msg_id=%s aibot_id=%s",
            native_feedback_id,
            feedback_type,
            content,
            reasons,
            user_id,
            body.get("chatid"),
            body.get("chattype"),
            body.get("msgid"),
            body.get("aibotid"),
        )
        if not isinstance(native_feedback_id, str) or not native_feedback_id:
            return

        repo = self._get_feedback_repo()
        record_channel_feedback = getattr(repo, "record_channel_feedback", None) if repo is not None else None
        if not callable(record_channel_feedback):
            return

        rating = self._map_feedback_type(feedback_type)
        comment = self._format_feedback_comment(content, reasons)
        try:
            saved = await record_channel_feedback(
                native_feedback_id=native_feedback_id,
                channel_name=self.name,
                rating=rating,
                platform_user_id=user_id if isinstance(user_id, str) else None,
                comment=comment,
            )
        except Exception:
            logger.exception("[WeCom] failed to persist feedback_event: feedback_id=%s", native_feedback_id)
            return
        if saved is None:
            logger.warning("[WeCom] feedback_event target not found or incomplete: feedback_id=%s", native_feedback_id)

    @staticmethod
    def _map_feedback_type(feedback_type: Any) -> int | None:
        try:
            value = int(feedback_type)
        except (TypeError, ValueError):
            return None
        if value == 1:
            return 1
        if value == 2:
            return -1
        return None

    @staticmethod
    def _format_feedback_comment(content: Any, reasons: Any) -> str | None:
        labels: list[str] = []
        if isinstance(reasons, list):
            for item in reasons:
                try:
                    code = int(item)
                except (TypeError, ValueError):
                    continue
                labels.append(_WECOM_FEEDBACK_REASON_LABELS.get(code, f"原因{code}"))
        parts: list[str] = []
        if labels:
            parts.append("；".join(labels))
        if isinstance(content, str) and content.strip():
            parts.append(f"补充反馈：{content.strip()}")
        return "\n".join(parts) if parts else None

    @staticmethod
    def _make_feedback_id(msg_id: str) -> str:
        feedback_id = f"deerflow:wecom:{msg_id}"
        if len(feedback_id) <= 256:
            return feedback_id
        digest = hashlib.sha256(msg_id.encode("utf-8")).hexdigest()
        return f"deerflow:wecom:{digest}"

    async def _upsert_feedback_target(
        self,
        *,
        native_feedback_id: str,
        chat_id: str | None,
        platform_user_id: str | None,
        platform_message_id: str | None,
        thread_id: str | None,
        run_id: str | None,
    ) -> None:
        repo = self._get_feedback_repo()
        upsert_channel_feedback_target = getattr(repo, "upsert_channel_feedback_target", None) if repo is not None else None
        if not callable(upsert_channel_feedback_target):
            return
        try:
            await upsert_channel_feedback_target(
                native_feedback_id=native_feedback_id,
                channel_name=self.name,
                chat_id=chat_id,
                platform_user_id=platform_user_id,
                platform_message_id=platform_message_id,
                thread_id=thread_id,
                run_id=run_id,
            )
        except Exception:
            logger.exception("[WeCom] failed to save feedback target: feedback_id=%s", native_feedback_id)

    async def _upsert_feedback_target_for_outbound(self, msg: OutboundMessage) -> None:
        if not msg.is_final or not msg.thread_ts:
            return
        run_id = msg.metadata.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            logger.warning("[WeCom] final outbound has no run_id for feedback target: msg_id=%s", msg.thread_ts)
            return
        platform_user_id = msg.metadata.get("platform_user_id")
        if not isinstance(platform_user_id, str) or not platform_user_id:
            platform_user_id = msg.chat_id
        await self._upsert_feedback_target(
            native_feedback_id=self._make_feedback_id(str(msg.thread_ts)),
            chat_id=msg.chat_id,
            platform_user_id=platform_user_id,
            platform_message_id=str(msg.thread_ts),
            thread_id=msg.thread_id,
            run_id=run_id,
        )

    async def _publish_ws_inbound(
        self,
        frame: dict[str, Any],
        text: str,
        *,
        files: list[dict[str, Any]] | None = None,
    ) -> None:
        if not self._ws_client:
            return
        try:
            from aibot import generate_req_id
        except Exception:
            return

        body = frame.get("body", {}) or {}
        msg_id = body.get("msgid")
        if not msg_id:
            return

        user_id = (body.get("from") or {}).get("userid")

        chattype = body.get("chattype")
        platform_chat_id = body.get("chatid") if chattype == "group" else user_id
        inbound_type = InboundMessageType.COMMAND if text.startswith("/") else InboundMessageType.CHAT
        inbound = self._make_inbound(
            chat_id=platform_chat_id,
            user_id=user_id,
            text=text,
            msg_type=inbound_type,
            thread_ts=msg_id,
            files=files or [],
            metadata={"aibotid": body.get("aibotid"), "chattype": chattype},
        )
        inbound.topic_id = user_id  # keep the same thread

        stream_id = generate_req_id("stream")
        self._ws_frames[msg_id] = frame
        self._ws_stream_ids[msg_id] = stream_id
        feedback_id = self._make_feedback_id(str(msg_id))

        try:
            await self._ws_client.reply_stream(
                frame,
                stream_id,
                self._working_message,
                False,
                feedback={"id": feedback_id},
            )
            logger.info(
                "[WeCom] native feedback enabled: feedback_id=%s user_id=%s msg_id=%s stream_id=%s",
                feedback_id,
                user_id,
                msg_id,
                stream_id,
            )
            await self._upsert_feedback_target(
                native_feedback_id=feedback_id,
                chat_id=platform_chat_id if isinstance(platform_chat_id, str) else None,
                platform_user_id=user_id if isinstance(user_id, str) else None,
                platform_message_id=str(msg_id),
                thread_id=None,
                run_id=None,
            )
            self._schedule_ws_stream_timeout(str(msg_id))
        except Exception:
            logger.warning("[WeCom] initial stream reply failed; using active-message fallback: msg_id=%s", msg_id, exc_info=True)
            self._detach_ws_stream(str(msg_id))

        await self.bus.publish_inbound(inbound)

    async def _send_ws(self, msg: OutboundMessage, *, _max_retries: int = 3) -> None:
        if not self._ws_client:
            return
        if msg.thread_ts and msg.thread_ts in self._detached_streams:
            if not msg.is_final:
                return
            await self._send_active_message(msg, _max_retries=_max_retries)
            return

        try:
            from aibot import generate_req_id
        except Exception:
            generate_req_id = None

        if msg.thread_ts and msg.thread_ts in self._ws_frames:
            frame = self._ws_frames[msg.thread_ts]
            stream_id = self._ws_stream_ids.get(msg.thread_ts)
            if not stream_id and generate_req_id:
                stream_id = generate_req_id("stream")
                self._ws_stream_ids[msg.thread_ts] = stream_id
            if not stream_id:
                return

            last_exc: Exception | None = None
            for attempt in range(_max_retries):
                try:
                    await self._ws_client.reply_stream(frame, stream_id, msg.text, bool(msg.is_final))
                    await self._upsert_feedback_target_for_outbound(msg)
                    return
                except Exception as exc:
                    last_exc = exc
                    if attempt < _max_retries - 1:
                        await asyncio.sleep(2**attempt)
            if last_exc:
                logger.warning(
                    "[WeCom] stream reply failed; switching to active-message fallback: msg_id=%s",
                    msg.thread_ts,
                    exc_info=last_exc,
                )
                self._detach_ws_stream(msg.thread_ts)
                if not msg.is_final:
                    return
                await self._send_active_message(msg, _max_retries=_max_retries)
                return

        await self._send_active_message(msg, _max_retries=_max_retries)

    async def _send_active_message(self, msg: OutboundMessage, *, _max_retries: int) -> None:
        if not self._ws_client:
            return
        body = {"msgtype": "markdown", "markdown": {"content": msg.text}}
        last_exc: Exception | None = None
        for attempt in range(_max_retries):
            try:
                await self._ws_client.send_message(msg.chat_id, body)
                return
            except Exception as exc:
                last_exc = exc
                if attempt < _max_retries - 1:
                    await asyncio.sleep(2**attempt)
        if last_exc:
            raise last_exc

    async def _upload_media_ws(
        self,
        *,
        media_type: str,
        filename: str,
        path: str,
        size: int,
    ) -> str | None:
        if not self._ws_client:
            return None
        try:
            from aibot import generate_req_id
        except Exception:
            return None

        chunk_size = 512 * 1024
        total_chunks = (size + chunk_size - 1) // chunk_size
        if total_chunks < 1 or total_chunks > 100:
            logger.warning("[WeCom] invalid total_chunks=%d for %s", total_chunks, filename)
            return None

        md5_hasher = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                md5_hasher.update(chunk)
        md5 = md5_hasher.hexdigest()

        init_req_id = generate_req_id("aibot_upload_media_init")
        init_body = {
            "type": media_type,
            "filename": filename,
            "total_size": int(size),
            "total_chunks": int(total_chunks),
            "md5": md5,
        }
        init_ack = await self._send_ws_upload_command(init_req_id, init_body, "aibot_upload_media_init")
        upload_id = (init_ack.get("body") or {}).get("upload_id")
        if not upload_id:
            logger.warning("[WeCom] upload init returned no upload_id: %s", init_ack)
            return None

        with open(path, "rb") as f:
            for idx in range(total_chunks):
                data = f.read(chunk_size)
                if not data:
                    break
                chunk_req_id = generate_req_id("aibot_upload_media_chunk")
                chunk_body = {
                    "upload_id": upload_id,
                    "chunk_index": int(idx),
                    "base64_data": base64.b64encode(data).decode("utf-8"),
                }
                await self._send_ws_upload_command(chunk_req_id, chunk_body, "aibot_upload_media_chunk")

        finish_req_id = generate_req_id("aibot_upload_media_finish")
        finish_ack = await self._send_ws_upload_command(finish_req_id, {"upload_id": upload_id}, "aibot_upload_media_finish")
        media_id = (finish_ack.get("body") or {}).get("media_id")
        if not media_id:
            logger.warning("[WeCom] upload finish returned no media_id: %s", finish_ack)
            return None
        return media_id
