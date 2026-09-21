from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from prisma.models import User

from api.auth.dependencies import get_current_user, require_admin
from db.client import db
import db.users.crud as crud

router = APIRouter()
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"


def _user_out(user: User) -> dict:
    return {
        "id": user.id, "email": user.email, "username": user.username,
        "is_admin": user.is_admin, "telegram_linked": user.telegram_id is not None,
    }


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.delete("/me")
async def delete_me(user: User = Depends(get_current_user)):
    await crud.delete_user(user.id)
    return {"status": "success", "message": "Account data deleted"}


@router.post("/me/telegram/link-code", status_code=201)
async def create_telegram_link_code(user: User = Depends(get_current_user)):
    if user.telegram_id:
        raise HTTPException(status_code=409, detail="Telegram is already linked")
    await db.telegramlinkcode.delete_many(where={"user_id": user.id, "used_at": None})
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    for _ in range(4):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        try:
            link = await db.telegramlinkcode.create(data={"code": code, "user_id": user.id, "expires_at": expires})
            stored_expiry = link.expires_at
            if stored_expiry.tzinfo is None:
                stored_expiry = stored_expiry.replace(tzinfo=timezone.utc)
            return {"code": link.code, "expires_at": stored_expiry.isoformat()}
        except Exception:
            continue
    raise HTTPException(status_code=503, detail="Could not generate a unique link code")


@router.delete("/me/telegram")
async def disconnect_telegram(user: User = Depends(get_current_user)):
    await db.user.update(where={"id": user.id}, data={"telegram_id": None})
    return {"status": "success", "message": "Telegram disconnected"}


@router.get("/")
async def get_users(_admin: User = Depends(require_admin)):
    return [_user_out(user) for user in await crud.get_users()]


@router.get("/{user_id}")
async def get_user(user_id: str, _admin: User = Depends(require_admin)):
    user = await crud.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_out(user)


@router.delete("/{user_id}")
async def delete_user(user_id: str, _admin: User = Depends(require_admin)):
    user = await crud.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await crud.delete_user(user_id)
    return {"status": "success", "message": "User deleted"}
