"""비밀 값 읽기: 배포에서는 Streamlit Secrets, 내 컴퓨터에서는 .env.

값을 화면이나 로그에 절대 출력하지 않는다(공고 4.1절, 6.3절 8번).
"""
from __future__ import annotations

import os

try:  # .env는 내 컴퓨터에서만 쓴다
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

DEFAULT_MODELS = [
    # 1차, 2차, 3차. OPENROUTER_MODELS(쉼표 구분)로 바꿀 수 있음. 모두 무료(:free) 모델.
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openai/gpt-oss-120b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]


def get(name: str, default: str | None = None) -> str | None:
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, default)


def models() -> list[str]:
    raw = get("OPENROUTER_MODELS")
    if raw:
        ms = [m.strip() for m in raw.split(",") if m.strip()]
        if ms:
            return ms[:3]
    return list(DEFAULT_MODELS)


def has(name: str) -> str:
    """키가 있는지 확인할 때는 '있음/없음'만 말한다."""
    return "있음" if get(name) else "없음"
