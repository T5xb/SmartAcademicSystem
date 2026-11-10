"""Password hashing (scrypt, standard library) and session tokens."""

import base64
import hashlib
import hmac
import secrets

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 200

# scrypt cost: 2**14 with r=8 uses about 16 MB and a few tens of milliseconds.
_N, _R, _P = 2**14, 8, 1


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Only this hash is stored, so a leaked table can't be used to sign in."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def temporary_password() -> str:
    """A one-time password the admin hands over; the user must change it."""
    return secrets.token_urlsafe(9)
