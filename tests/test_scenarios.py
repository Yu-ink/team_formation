"""공고 부록의 연습용 시나리오 3개를 서비스 함수로 처음부터 끝까지 돌려 기대 결과와 비교한다.

실행: TEST_DATABASE_URL="postgresql://...(연습용 DB)" python -m tests.test_scenarios
주의: 이 테스트는 tf_ 테이블을 모두 지운다. 실제 채점용 DB가 아닌 연습용 DB에서만 돌린다.
AI는 진짜로 부르지 않고, 1차 시간 초과 → 2차 빈 응답 → 3차 규칙 위반 → 앱 직접 배정 흐름을 흉내 낸다.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from tf import ai, rules, service

DATA = Path(__file__).resolve().parent.parent / "data"

# (동작, ...인자, 기대 첫 단어). 학생은 '학생N' 줄임 이름으로 적는다.
EASY = ("쉬움.csv", 3, [
    ("apply", "학생1", 1, "승인"), ("apply", "학생2", 2, "승인"), ("apply", "학생3", 3, "승인"),
    ("apply", "학생4", 1, "대기"), ("vote", "학생1", "학생4", True, "승인"),
    ("apply", "학생5", 2, "대기"), ("vote", "학생2", "학생5", True, "승인"),
    ("apply", "학생7", 1, "대기"), ("vote", "학생1", "학생7", True, "대기"), ("vote", "학생4", "학생7", False, "거절"),
    ("apply", "학생6", 3, "대기"), ("vote", "학생3", "학생6", True, "승인"),
    ("close", "승인", None),
    ("assign",),
])

MID = ("중간.csv", 4, [
    ("apply", "학생1", 1, "승인"),
    ("apply", "학생5", 1, "대기"), ("vote", "학생1", "학생5", True, "승인"),
    ("apply", "학생2", 1, "막힘"),  # 주 역할 중복 → 뒤의 투표는 건너뜀
    ("apply", "학생6", 2, "승인"),
    ("apply", "학생9", 2, "대기"), ("vote", "학생6", "학생9", True, "승인"),
    ("apply", "학생10", 2, "대기"), ("vote", "학생6", "학생10", True, "대기"), ("vote", "학생9", "학생10", False, "거절"),
    ("apply", "학생3", 3, "승인"), ("apply", "학생11", 4, "승인"),
    ("apply", "학생12", 4, "대기"), ("apply", "학생12", 3, "막힘"),
    ("close", "승인", ["학생2", "학생3", "학생4", "학생7", "학생8", "학생10", "학생11", "학생12"]),
    ("apply", "학생2", 3, "막힘"),
    ("assign",),
])

HARD = ("어려움.csv", 4, [
    ("apply", "학생1", 1, "승인"),
    ("apply", "학생4", 1, "대기"), ("vote", "학생1", "학생4", True, "승인"),
    ("apply", "학생7", 1, "대기"), ("vote", "학생1", "학생7", True, "대기"), ("vote", "학생4", "학생7", True, "승인"),
    ("apply", "학생2", 2, "승인"),
    ("apply", "학생8", 2, "대기"), ("vote", "학생2", "학생8", True, "승인"),
    ("apply", "학생5", 2, "대기"), ("apply", "학생6", 2, "대기"),
    ("vote", "학생2", "학생5", True, "대기"), ("vote", "학생8", "학생5", True, "승인"),
    ("vote", "학생2", "학생6", True, "대기"), ("vote", "학생8", "학생6", True, "대기"),
    ("vote", "학생5", "학생6", True, "거절"),  # 승인 직전 검사(주 역할 중복)
    ("apply", "학생11", 3, "승인"),
    ("apply", "학생15", 3, "대기"), ("vote", "학생11", "학생15", True, "승인"),
    ("apply", "학생14", 3, "막힘"),  # 필수 포함 역할 자리
    ("apply", "학생10", 4, "승인"),
    ("apply", "학생13", 1, "대기"), ("vote", "학생1", "학생13", True, "대기"),
    ("close", "승인", ["학생3", "학생6", "학생9", "학생10", "학생12", "학생13", "학생14", "학생16"]),
    ("assign",),
])


def short(name):
    return name.split("(")[0]


def run(db, scenario, ai_mode="fail_all"):
    csv_name, team_count, steps = scenario
    word, msg = service.reset_roster(db, (DATA / csv_name).read_bytes(), team_count)
    assert word == "승인", msg
    s = service.read_state(db)
    no = {short(x.name): x.student_no for x in s.students.values()}
    fails = 0
    for i, step in enumerate(steps, 1):
        kind = step[0]
        if kind == "apply":
            _, who, team, want = step
            got = service.apply(db, no[who], team)
        elif kind == "vote":
            _, voter, applicant, yes, want = step
            st = service.read_state(db)
            app = st.pending_of(st.by_no[no[applicant]].id) or st.latest_app(st.by_no[no[applicant]].id)
            got = service.vote(db, no[voter], app.id, yes)
        elif kind == "close":
            _, want, expect_un = step
            got = service.close(db)
            if expect_un is not None:
                un = sorted(short(x.name) for x in service.read_state(db).unassigned())
                if un != sorted(expect_un):
                    print(f"  ✗ 마감 뒤 팀 없는 학생 {un} != {sorted(expect_un)}"); fails += 1
        elif kind == "assign":
            got, want = do_assign(db, ai_mode), "승인"
        ok = got[0] == want
        fails += not ok
        print(f"  {'✓' if ok else '✗'} {i:2d}. {step[:-1] if kind != 'assign' else 'assign+confirm'} → {got[0]}: {got[1]}"
              + ("" if ok else f"   (기대: {want})"))
    final = service.read_state(db)
    errs = rules.final_team_errors(final.team_dict())
    left = final.unassigned()
    print("  최종:", {t.name: [short(m.name) for m in t.members] for t in final.teams})
    if errs or left:
        print("  ✗ 최종 팀 구성 규칙 위반:", errs, [x.name for x in left]); fails += 1
    else:
        print("  ✓ 최종 팀 구성이 모든 규칙을 지킴")
    return fails


def fake_call_factory(mode, teams, unassigned):
    good = rules.solve(teams, unassigned)

    def call(model, prompt, key):
        idx = [m for m in __import__("tf.config", fromlist=["models"]).models()].index(model)
        if mode == "fail_all":
            if idx == 0:
                time.sleep(3)  # 시간 초과(테스트에서는 제한을 2초로 줄임)
                return ""
            if idx == 1:
                return ""  # 빈 응답
            # 3차: 규칙을 어긴 답(모두 팀1)
            return json.dumps({"assignments": [{"student_no": s.student_no, "team": "팀1"} for s in unassigned]})
        if mode == "first_ok":
            return "```json\n" + json.dumps({"assignments": [{"student_no": n, "team": t} for n, t in good]}) + "\n```"
        raise AssertionError(mode)

    return call


def do_assign(db, mode):
    s, teams, unassigned = service.assignment_input(db)
    steps = []
    out = ai.assign(teams, unassigned, on_progress=steps.append, call=fake_call_factory(mode, teams, unassigned),
                    limit_sec=2, log=lambda *a: service.log_ai(db, *a))
    print("     AI:", [(a["차수"], a["결과"]) for a in out["attempts"]], "→", out["source"])
    if not out["ok"]:
        return "막힘", out["message"]
    return service.confirm(db, out["plan"])


def main(db):
    os.environ.setdefault("OPENROUTER_API_KEY", "test-dummy")
    total = 0
    for name, sc, mode in [("쉬움", EASY, "first_ok"), ("중간", MID, "fail_all"), ("어려움", HARD, "fail_all")]:
        print(f"[{name}] AI 흉내: {mode}")
        total += run(db, sc, mode)
    print("실패", total, "건")
    return total


if __name__ == "__main__":
    from tf.db import Database

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        sys.exit("TEST_DATABASE_URL(연습용 DB 주소)을 넣고 실행하세요")
    d = Database(url)
    d.apply_schema()
    sys.exit(1 if main(d) else 0)
