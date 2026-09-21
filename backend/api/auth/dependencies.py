from __future__ import annotations

import os
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from prisma.models import User

from db.client import db

ASYMMETRIC_ALGS = ("RS256", "ES256", "EdDSA")
_bearer = HTTPBearer(auto_error=False)


def _settings() -> tuple[str, str, str | None]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise HTTPException(status_code=503, detail="SUPABASE_URL is not configured")
    issuer = f"{url}/auth/v1"
    return issuer, f"{issuer}/.well-known/jwks.json", os.getenv("SUPABASE_JWT_SECRET")


@lru_cache(maxsize=1)
def jwks_client() -> PyJWKClient:
    return PyJWKClient(_settings()[1], cache_jwk_set=True, lifespan=600)


def _decode_token(token: str) -> dict:
    issuer, _jwks_url, legacy_secret = _settings()
    alg = jwt.get_unverified_header(token).get("alg")
    if alg in ASYMMETRIC_ALGS:
        key, algorithms = jwks_client().get_signing_key_from_jwt(token).key, [alg]
    elif alg == "HS256":
        if not legacy_secret:
            raise jwt.InvalidAlgorithmError("Legacy HS256 secret is not configured")
        key, algorithms = legacy_secret, ["HS256"]
    else:
        raise jwt.InvalidAlgorithmError(f"Unsupported signing algorithm: {alg}")
    return jwt.decode(
        token, key, algorithms=algorithms, audience="authenticated", issuer=issuer,
        leeway=10, options={"require": ["exp", "iat", "sub", "aud", "iss"]},
    )


async def prefetch_jwks() -> None:
    _settings()
    await run_in_threadpool(jwks_client().get_jwk_set)


async def _user_from_credentials(credentials: HTTPAuthorizationCredentials) -> User:
    try:
        claims = await run_in_threadpool(_decode_token, credentials.credentials)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc
    subject = str(claims["sub"])
    email = claims.get("email")
    user = await db.user.find_unique(where={"supabase_user_id": subject})
    if user:
        if email and user.email != email:
            user = await db.user.update(where={"id": user.id}, data={"email": email})
        return user
    try:
        return await db.user.create(data={"supabase_user_id": subject, "email": email, "username": email})
    except Exception:
        user = await db.user.find_unique(where={"supabase_user_id": subject})
        if user:
            return user
        raise


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return await _user_from_credentials(credentials)


async def get_current_user_optional(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User | None:
    if credentials is None:
        return None
    return await _user_from_credentials(credentials)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user
