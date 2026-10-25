import hashlib
import hmac
import secrets


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, expected = stored.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False
