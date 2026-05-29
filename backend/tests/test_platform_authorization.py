from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _request():
    return SimpleNamespace(state=SimpleNamespace(), cookies={})


@pytest.mark.anyio
async def test_require_admin_allows_admin(monkeypatch):
    from app.gateway.auth.models import User
    import app.gateway.authz as authz

    async def fake_authenticate(_request):
        return authz.AuthContext(user=User(email="admin@example.com", system_role="admin"))

    monkeypatch.setattr(authz, "_authenticate", fake_authenticate)

    @authz.require_admin
    async def handler(*, request):
        return {"ok": True, "user": request.state.auth.user.email}

    assert await handler(request=_request()) == {"ok": True, "user": "admin@example.com"}


@pytest.mark.anyio
async def test_require_admin_rejects_normal_user(monkeypatch):
    from app.gateway.auth.models import User
    import app.gateway.authz as authz

    async def fake_authenticate(_request):
        return authz.AuthContext(user=User(email="user@example.com", system_role="user"))

    monkeypatch.setattr(authz, "_authenticate", fake_authenticate)

    @authz.require_admin
    async def handler(*, request):
        return {"ok": True}

    with pytest.raises(HTTPException) as exc:
        await handler(request=_request())

    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_require_admin_rejects_anonymous(monkeypatch):
    import app.gateway.authz as authz

    async def fake_authenticate(_request):
        return authz.AuthContext(user=None)

    monkeypatch.setattr(authz, "_authenticate", fake_authenticate)

    @authz.require_admin
    async def handler(*, request):
        return {"ok": True}

    with pytest.raises(HTTPException) as exc:
        await handler(request=_request())

    assert exc.value.status_code == 401
