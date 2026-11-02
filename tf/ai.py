"""AI 배정: 오픈라우터 무료 모델 1차 → 2차 → 3차, 모두 실패하면 앱이 직접 배정.

- 모델마다 120초의 '전체' 대기 시간을 직접 잰다(요청을 다른 스레드에서 보내고 시계를 본다).
  응답이 천천히 흘러와도 120초가 지나면 끊고 다음 모델로 넘어간다(3장 어려운 해결).
- 빈 응답, 오류, HTTP 429, JSON이 아닌 답, 규칙 검사 실패를 모두 실패로 본다.
- 무료 모델 자동 라우터(openrouter/free)는 쓰지 않는다.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from . import config, rules

URL = "https://openrouter.ai/api/v1/chat/completions"
LIMIT_SEC = 120


def build_prompt(teams: dict, unassigned: list) -> str:
    lines = [
        "너는 대학 팀 프로젝트의 팀 편성을 돕는다. 아래 '팀이 없는 학생'을 기존 팀에 배정하라.",
        "",
        "[규칙]",
        "1. 팀이 없는 학생은 빠짐없이 정확히 한 팀에 배정한다. 이미 팀에 있는 학생은 옮기지 않는다.",
        "2. 배정 뒤 모든 팀은 2~4명이어야 한다(빈 팀이 있으면 안 됨).",
        "3. 한 팀 안에서 '주 역할'이 같은 학생이 2명 이상이면 안 된다(보조 역할은 겹쳐도 됨).",
        "4. 모든 팀에 '기획자'를 맡을 학생과 '웹 프로그래머'를 맡을 학생이 서로 다른 사람으로 1명씩 있어야 한다.",
        "   주 역할 또는 보조 역할로 맡을 수 있다. 한 학생이 둘 다 할 수 있어도 한 역할로만 센다.",
        "",
        "[지금 팀 구성]",
    ]
    for t, ms in teams.items():
        if ms:
            body = "; ".join(f"{m.name}(주 {m.main_role} / 보조 {', '.join(m.sub_roles) or '없음'})" for m in ms)
        else:
            body = "(빈 팀)"
        lines.append(f"- {t} ({len(ms)}명): {body}")
    lines += ["", "[팀이 없는 학생]"]
    for s in unassigned:
        lines.append(f"- 학번 {s.student_no}, {s.name}, 주 역할 {s.main_role}, 보조 역할 {', '.join(s.sub_roles) or '없음'}")
    lines += [
        "",
        "[답 형식] 설명 없이 JSON 하나만 출력하라. 팀 이름은 위에 적힌 그대로 쓴다.",
        '{"assignments": [{"student_no": "학번", "team": "팀1"}, ...]}',
    ]
    return "\n".join(lines)


def parse_plan(text: str):
    """모델의 답에서 [(학번, 팀이름), ...]을 꺼낸다. 실패하면 ValueError."""
    if not text or not text.strip():
        raise ValueError("빈 응답")
    t = re.sub(r"```(?:json)?", "", text).strip()
    start = t.find("{")
    if start < 0:
        raise ValueError("JSON이 없음")
    obj, _ = json.JSONDecoder().raw_decode(t[start:])
    items = obj.get("assignments") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        raise ValueError("assignments 목록이 없음")
    plan = []
    for it in items:
        if not isinstance(it, dict):
            raise ValueError("assignments 항목 형식이 다름")
        plan.append((str(it.get("student_no", "")).strip(), str(it.get("team", "")).strip()))
    return plan


def _call(model: str, prompt: str, key: str) -> str:
    resp = requests.post(
        URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "tf-team-formation"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 8000,  # 추론 모델이 생각하는 데 다 써서 빈 응답을 내지 않도록 넉넉히
            "reasoning": {"effort": "low"},
        },
        timeout=(10, LIMIT_SEC),
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    data = resp.json()
    if "error" in data:
        code = data["error"].get("code") if isinstance(data["error"], dict) else ""
        raise RuntimeError(f"오류 응답 {code}".strip())
    choices = data.get("choices") or []
    content = (choices[0].get("message") or {}).get("content") if choices else None
    return content or ""


def assign(teams: dict, unassigned: list, on_progress=None, log=None, call=None, limit_sec: int = LIMIT_SEC):
    """배정안을 만든다.

    on_progress(text): 화면에 지금 무엇을 기다리는지 보여 주는 함수
    log(attempt, model, outcome, elapsed_ms, detail): AI 호출 기록 함수
    call(model, prompt, key): 테스트에서 바꿔 끼우는 호출 함수
    반환: {"ok", "plan", "source", "attempts", "message"}
    """
    on_progress = on_progress or (lambda _t: None)
    log = log or (lambda *a, **k: None)
    call = call or _call
    attempts = []

    # 규칙을 지키는 배정이 아예 없으면 AI를 부르지 않는다(2.5절 8항)
    if rules.solve(teams, unassigned) is None:
        return {"ok": False, "plan": None, "source": None, "attempts": attempts,
                "message": "규칙을 지키는 배정이 없음: " + rules.explain_no_solution(teams, unassigned)}
    if not unassigned:
        return {"ok": True, "plan": [], "source": "배정할 학생 없음", "attempts": attempts,
                "message": "팀이 없는 학생이 없고 지금 팀 구성이 규칙을 지킴"}

    key = config.get("OPENROUTER_API_KEY")
    prompt = build_prompt(teams, unassigned)
    models = config.models()
    for i, model in enumerate(models, start=1):
        label = f"{i}차 모델({model})"
        start = time.monotonic()
        outcome, detail, plan = "실패", "", None
        if not key:
            outcome, detail = "키 없음", "OPENROUTER_API_KEY가 없음"
        else:
            pool = ThreadPoolExecutor(max_workers=1)
            fut = pool.submit(call, model, prompt, key)
            try:
                while not fut.done():
                    el = time.monotonic() - start
                    if el >= limit_sec:
                        break
                    on_progress(f"{label}의 응답을 기다리는 중… {int(el)}초 / {limit_sec}초")
                    time.sleep(0.5)
                if not fut.done():
                    outcome, detail = "시간 초과", f"{limit_sec}초 안에 응답하지 않음"
                else:
                    try:
                        text = fut.result()
                        plan = parse_plan(text)
                        errs = rules.validate_plan(teams, unassigned, plan)
                        if errs:
                            outcome, detail, plan = "규칙 위반", "; ".join(errs[:3]), None
                        else:
                            outcome = "성공"
                    except ValueError as e:
                        outcome, detail = ("빈 응답" if str(e) == "빈 응답" else "형식 오류"), str(e)
                    except requests.Timeout:
                        outcome, detail = "시간 초과", "연결 또는 응답 시간 초과"
                    except Exception as e:  # HTTP 429 등. 키나 주소는 문장에 넣지 않는다
                        outcome, detail = "호출 실패", str(e)[:120]
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
        ms = int((time.monotonic() - start) * 1000)
        attempts.append({"차수": f"{i}차", "모델": model, "결과": outcome, "걸린 시간(초)": round(ms / 1000, 1), "내용": detail})
        log(i, model, outcome, ms, detail)
        if outcome == "성공":
            return {"ok": True, "plan": plan, "source": label, "attempts": attempts,
                    "message": f"{label}의 배정안이 검사 다섯 가지를 통과함"}
        on_progress(f"{label} 실패({outcome}). 다음으로 넘어감")

    # 3차까지 실패 → 앱이 모든 경우를 따져 직접 배정
    on_progress("AI 3개 모델이 모두 실패해 앱이 모든 경우를 따져 직접 배정하는 중…")
    plan = rules.solve(teams, unassigned)
    log(len(models) + 1, "앱 직접 배정", "성공" if plan is not None else "실패", 0, "")
    errs = rules.validate_plan(teams, unassigned, plan) if plan is not None else ["배정 없음"]
    if plan is None or errs:
        return {"ok": False, "plan": None, "source": None, "attempts": attempts,
                "message": "규칙을 지키는 배정이 없음: " + rules.explain_no_solution(teams, unassigned)}
    return {"ok": True, "plan": plan, "source": "앱 직접 배정(AI 3개 모델 모두 실패)", "attempts": attempts,
            "message": "AI가 모두 실패해 앱이 규칙을 모두 지키는 배정을 찾음(검사 다섯 가지 통과)"}
