"""Authentication dependency: validate Supabase JWT from Authorization bearer.

The browser sends the user's access token (issued by Supabase Auth) as:
    Authorization: Bearer <access_token>

Hosted Supabase projects sign user access tokens with ES256 (ECDSA) and expose
the corresponding public keys (JWKS) at
    https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json

The backend resolves the signing key by the token's `kid` (so key rotation
keeps working), verifies the signature, audience, and expiry, then extracts the
`sub` claim as the user id. Keys are cached by PyJWKClient so there is at most
one JWKS fetch per server process.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import TYPE_CHECKING

import jwt
from fastapi import Depends, Header, HTTPException, status

from .config import get_settings

if TYPE_CHECKING:
    from dataclasses import dataclass
else:
    from dataclasses import dataclass


@dataclass(frozen=True)
class UserContext:
    user_id: str
    email: str | None = None


credential_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing authentication credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


@lru_cache(maxsize=1)
def _get_jwk_client() -> jwt.PyJWKClient:
    settings = get_settings()
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return jwt.PyJWKClient(url, cache_keys=True)


def _decode_token(token: str) -> dict:
    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError:
        raise credential_error

    exp = payload.get("exp", 0)
    if exp < time.time():
        raise credential_error

    return payload


async def require_user(
    authorization: str | None = Header(default=None),
) -> UserContext:
    """Dependency that returns the authenticated user context, or 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise credential_error

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise credential_error

    payload = _decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise credential_error

    return UserContext(user_id=user_id, email=payload.get("email"))
