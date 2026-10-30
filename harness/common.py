"""Shared helpers for the mock APIM gateway and the fake `az`: key handling and JWT minting."""
import json
import pathlib
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ROOT = pathlib.Path(__file__).parent
KEYS = ROOT / "keys"
LOGS = ROOT / "logs"
ISSUER = "https://login.microsoftonline.com/00000000-0000-0000-0000-00000000test/v2.0"
AUDIENCE = "api://apim-test"
KID = "test-key-1"


def private_key():
    KEYS.mkdir(exist_ok=True)
    pem = KEYS / "private.pem"
    if not pem.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    return serialization.load_pem_private_key(pem.read_bytes(), None)


def jwks():
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key().public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


def mint(ttl=120, aud=AUDIENCE, upn="user@test.example", now=None, extra=None):
    now = int(now if now is not None else time.time())
    claims = {
        "iss": ISSUER,
        "aud": aud,
        "iat": now,
        "nbf": now,
        "exp": now + int(ttl),
        "jti": uuid.uuid4().hex,
        "upn": upn,
        "oid": "11111111-1111-1111-1111-111111111111",
        "scp": "access_as_user",
    }
    claims.update(extra or {})
    return jwt.encode(claims, private_key(), algorithm="RS256", headers={"kid": KID})

