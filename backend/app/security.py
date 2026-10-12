import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import bcrypt
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from .config import settings


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite does not keep timezone info)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_epoch(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


# ---------------------------------------------------------------- passwords

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


@lru_cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check so unknown usernames can't be detected by timing."""
    verify_password(password, _dummy_hash())


# ---------------------------------------------------------------- opaque tokens

def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_pkce(verifier: str, challenge: str) -> bool:
    digest = hashlib.sha256(verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(expected, challenge)


# ---------------------------------------------------------------- JWT signing

class SigningKeys:
    """RS256 key pair used to sign ID/access tokens. Client systems verify with the JWKS endpoint."""

    def __init__(self) -> None:
        self._private = None
        self._public = None
        self.kid = ""

    def load(self, keys_dir: str) -> None:
        path = Path(keys_dir)
        path.mkdir(parents=True, exist_ok=True)
        pem_file = path / "private.pem"
        if pem_file.exists():
            key = serialization.load_pem_private_key(pem_file.read_bytes(), password=None)
        else:
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            pem_file.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        self._private = key
        self._public = key.public_key()
        der = self._public.public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.kid = hashlib.sha256(der).hexdigest()[:16]

    def sign(self, claims: dict) -> str:
        return jwt.encode(claims, self._private, algorithm="RS256", headers={"kid": self.kid})

    def verify(self, token: str, audience: str | None = None) -> dict:
        return jwt.decode(
            token,
            self._public,
            algorithms=["RS256"],
            issuer=settings.issuer,
            audience=audience,
            options={"verify_aud": audience is not None},
        )

    def public_pem(self) -> str:
        """The public key as a PEM file, for apps that verify tokens with a key file instead of JWKS."""
        return self._public.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()

    def public_jwk(self) -> dict:
        jwk = json.loads(RSAAlgorithm.to_jwk(self._public))
        jwk.update({"kid": self.kid, "use": "sig", "alg": "RS256"})
        return jwk


signing_keys = SigningKeys()
