"""비밀번호 해시(bcrypt). 원래 비밀번호는 DB에 저장하지 않는다(공고 3장, 6.3절 10번)."""
from __future__ import annotations

import bcrypt


def hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def check_pw(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False
