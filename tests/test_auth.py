import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def ecdsa_keys():
    """Generate an ephemeral ES256 key pair for offline JWT tests."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_pem


class _FakeSigningKey:
    def __init__(self, public_pem: bytes):
        self.key = public_pem


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch, ecdsa_keys):
    _, public_pem = ecdsa_keys

    class _FakeClient:
        def get_signing_key_from_jwt(self, token):  # noqa: ARG002
            return _FakeSigningKey(public_pem)

    monkeypatch.setattr("app.auth._get_jwk_client", lambda: _FakeClient())
    yield


def _make_token(private_key, sub: str = "user-123", *, aud: str = "authenticated", exp: float | None = None):
    now = time.time()
    payload = {
        "sub": sub,
        "aud": aud,
        "iat": int(now),
        "exp": int(exp if exp is not None else now + 3600),
        "email": "user@example.com",
    }
    return jwt.encode(payload, private_key, algorithm="ES256")


def test_health_public():
    assert client.get("/v1/health").status_code == 200


def test_protected_rejects_missing_token():
    assert client.get("/v1/documents").status_code == 401


def test_protected_rejects_garbage_token():
    r = client.get("/v1/documents", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_decode_valid_token(ecdsa_keys):
    private_key, _ = ecdsa_keys
    ctx = auth._decode_token(_make_token(private_key))
    assert ctx["sub"] == "user-123"
    assert ctx["email"] == "user@example.com"


def test_decode_rejects_bad_audience(ecdsa_keys):
    private_key, _ = ecdsa_keys
    with pytest.raises(HTTPException):
        auth._decode_token(_make_token(private_key, aud="something_else"))


def test_decode_rejects_expired(ecdsa_keys):
    private_key, _ = ecdsa_keys
    with pytest.raises(HTTPException):
        auth._decode_token(_make_token(private_key, exp=time.time() - 10))
