"""Password hashing. Uses the maintained `bcrypt` library directly (passlib is
unmaintained and breaks against modern bcrypt)."""

import bcrypt

# bcrypt hashes at most the first 72 bytes of input; we truncate explicitly so
# longer inputs hash deterministically instead of raising.
_MAX_BYTES = 72


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    pw = password.encode("utf-8")[:_MAX_BYTES]
    return bcrypt.checkpw(pw, hashed.encode("utf-8"))
