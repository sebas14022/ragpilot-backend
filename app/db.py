"""Shared Supabase service-role client and thin RPC helpers.

The backend authenticates to Supabase with the **service_role** key so it can
bypass RLS and manage vectors / storage on behalf of any user (the frontend
keeps using the anon key + JWT). The browser is therefore never given this key.
"""

from __future__ import annotations

from functools import lru_cache

import httpx
from supabase import Client, ClientOptions, create_client

from .config import get_settings

# postgrest-py hardcodes ``httpx.Client(http2=True)``. With HTTP/2, httpcore
# multiplexes everything over one long-lived connection and caches the first
# read failure on it (``_read_exception``); when the link blips, every later
# request re-raises the old ``RemoteProtocolError: Server disconnected``
# instead of opening a fresh socket — the server ends up permanently unable to
# reach Supabase until it is restarted. Plain HTTP/1.1 hands the failure back
# to the connection pool, which discards the dead socket on the next request.
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=10.0)


@lru_cache
def _http_client() -> httpx.Client:
    return httpx.Client(
        http2=False,
        timeout=_HTTP_TIMEOUT,
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=5,
            keepalive_expiry=15.0,
        ),
    )


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=ClientOptions(httpx_client=_http_client()),
    )


def get_user_email(client: Client, user_id: str) -> str | None:
    try:
        res = client.auth.admin.get_user_by_id(user_id)
        return getattr(getattr(res, "user", None), "email", None)
    except Exception:
        return None
