"""팀 편성 규칙 (DB, 화면과 무관한 순수 함수).

공고 2.3절(팀 규칙), 2.4절(지원과 투표), 2.5절(배정안 검사)과
3장의 어려운 해결(필수 포함 역할 자리 지키기, 3차 실패 시 모든 경우 탐색)을 담는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PL = "기획자"
WP = "웹 프로그래머"
FD = "프론트엔드 디자이너"
TT = "테스터"
RW = "보고서 작성자"
PT = "발표자"
ROLES = (PL, WP, FD, TT, RW, PT)
ABBR = {PL: "PL", WP: "WP", FD: "FD", TT: "TT", RW: "RW", PT: "PT"}
REQUIRED = (PL, WP)

MIN_SIZE = 2
MAX_SIZE = 4


@dataclass(frozen=True)
class Student:
    id: int
    student_no: str
    name: str
    main_role: str
    sub_roles: tuple = field(default_factory=tuple)

    def can(self, role: str) -> bool:
        return self.main_role == role or role in self.sub_roles

    def roles_text(self) -> str:
        subs = ", ".join(self.sub_roles) if self.sub_roles else "없음"
        return f"주 역할 {self.main_role} · 보조 {subs}"


# ---------------------------------------------------------------- 필수 포함 역할
def required_cover(members) -> list[str]:
    """기획자, 웹 프로그래머를 서로 다른 사람이 맡도록 했을 때 아직 못 채운 역할 목록.

    한 학생이 둘 다 할 수 있어도 하나로만 센다(공고 3장 아래 설명).
    반환값의 길이 = 아직 채우지 못한 필수 포함 역할 수.
    """
    members = list(members)
    pl = [m for m in members if m.can(PL)]
    wp = [m for m in members if m.can(WP)]
    # 서로 다른 두 사람으로 둘 다 채울 수 있는가
    for a in pl:
        for b in wp:
            if a.student_no != b.student_no:
                return []
    if not pl and not wp:
        return [PL, WP]
    if not pl:
        return [PL]
    if not wp:
        return [WP]
    # 둘 다 할 수 있는 사람이 딱 한 명뿐 → 한 역할만 채운 셈
    return [f"{PL} 또는 {WP} 중 하나"]


def join_block_reason(members, applicant: Student) -> str | None:
    """applicant가 members 팀에 들어갈 때 어기는 규칙. 없으면 None.

    지원할 때(막힘)와 승인 직전 재검사(거절)에 같은 함수를 쓴다.
    """
    members = list(members)
    if len(members) >= MAX_SIZE:
        return "팀이 꽉 참(4명)"
    if any(m.main_role == applicant.main_role for m in members):
        return "같은 주 역할의 팀원이 있음"
    after = members + [applicant]
    missing = required_cover(after)
    remaining = MAX_SIZE - len(after)
    if len(missing) > remaining:
        return (
            "필수 포함 역할을 맡을 학생의 자리가 모자람"
            f"(들어간 뒤 남는 자리 {remaining}개, 채울 역할 {len(missing)}개: {', '.join(missing)})"
        )
    return None


# ---------------------------------------------------------------- 배정안 검사
def validate_plan(teams: dict, unassigned: list, plan: list) -> list[str]:
    """배정안 검사 다섯 가지(공고 2.5절 4항). 오류 문장 목록을 돌려준다(비면 통과).

    teams: {팀이름: [Student, ...]}  (마감 뒤 현재 팀원)
    unassigned: [Student, ...]       (팀이 없는 학생)
    plan: [(학번, 팀이름), ...]
    """
    errors: list[str] = []
    by_no = {s.student_no: s for s in unassigned}
    placed_already = {m.student_no for ms in teams.values() for m in ms}
    seen: dict[str, str] = {}

    # 2) 한 학생은 한 팀에만
    for no, team in plan:
        no = str(no).strip()
        if no in seen and seen[no] != team:
            errors.append(f"{_nm(by_no, no)}이(가) 두 팀({seen[no]}, {team})에 배정됨")
        elif no in seen:
            errors.append(f"{_nm(by_no, no)}이(가) 두 번 배정됨")
        seen[no] = team

    # 1) 팀이 없는 학생이 빠짐없이, 그리고 그 학생만
    for no in seen:
        if no in placed_already:
            errors.append(f"이미 팀이 있는 학생({no})을 옮기려 함")
        elif no not in by_no:
            errors.append(f"명단에 없는 학번({no})")
    for s in unassigned:
        if s.student_no not in seen:
            errors.append(f"{s.name}이(가) 배정되지 않음")
    for no, team in seen.items():
        if team not in teams:
            errors.append(f"없는 팀({team})에 배정됨")

    if errors:
        return errors

    final = {t: list(ms) for t, ms in teams.items()}
    for no, team in seen.items():
        final[team].append(by_no[no])
    errors.extend(final_team_errors(final))
    return errors


def final_team_errors(final: dict) -> list[str]:
    """확정할 팀 구성 전체에 대한 검사 3)~5)."""
    errors = []
    for team, ms in final.items():
        if not (MIN_SIZE <= len(ms) <= MAX_SIZE):
            errors.append(f"{team} 인원이 {len(ms)}명(2~4명이어야 함)")
        mains = [m.main_role for m in ms]
        dup = sorted({r for r in mains if mains.count(r) > 1})
        if dup:
            errors.append(f"{team}에 주 역할 중복({', '.join(dup)})")
        miss = required_cover(ms)
        if miss:
            errors.append(f"{team}에 {', '.join(miss)}을(를) 맡을 학생이 없음")
    return errors


def _nm(by_no, no):
    s = by_no.get(no)
    return s.name if s else no


# ---------------------------------------------------------------- 앱이 직접 배정(모든 경우 탐색)
def solve(teams: dict, unassigned: list):
    """규칙을 모두 지키는 배정을 백트래킹으로 끝까지 찾는다.

    찾으면 [(학번, 팀이름), ...], 없으면 None.
    """
    names = list(teams.keys())
    cur = {t: list(ms) for t, ms in teams.items()}
    students = list(unassigned)

    # 갈 수 있는 팀이 적은 학생부터(가지치기 효과가 큼)
    def options(s):
        return [t for t in names if len(cur[t]) < MAX_SIZE and all(m.main_role != s.main_role for m in cur[t])]

    students.sort(key=lambda s: (len(options(s)), s.student_no))
    plan: list = []

    def feasible_rest(i):
        left = len(students) - i
        need_min = sum(max(0, MIN_SIZE - len(cur[t])) for t in names)
        if need_min > left:
            return False
        free = sum(MAX_SIZE - len(cur[t]) for t in names)
        if free < left:
            return False
        for t in names:
            if len(required_cover(cur[t])) > MAX_SIZE - len(cur[t]):
                return False
        return True

    def rec(i):
        if not feasible_rest(i):
            return False
        if i == len(students):
            return not final_team_errors(cur)
        s = students[i]
        # 인원이 적은 팀, 필수 역할이 빈 팀을 먼저 시도
        order = sorted(
            options(s),
            key=lambda t: (-(len(required_cover(cur[t])) > 0 and (s.can(PL) or s.can(WP))), len(cur[t]), t),
        )
        # options()가 인원·주 역할 중복을 거르고, 필수 역할은 feasible_rest와 마지막 검사가 본다
        for t in order:
            cur[t].append(s)
            plan.append((s.student_no, t))
            if rec(i + 1):
                return True
            plan.pop()
            cur[t].pop()
        return False

    return list(plan) if rec(0) else None


def explain_no_solution(teams: dict, unassigned: list) -> str:
    """규칙을 지키는 배정이 없을 때 사람이 읽을 이유."""
    reasons = []
    left = len(unassigned)
    free = sum(MAX_SIZE - len(ms) for ms in teams.values())
    need_min = sum(max(0, MIN_SIZE - len(ms)) for ms in teams.values())
    if free < left:
        reasons.append(f"남은 자리({free}개)보다 팀이 없는 학생({left}명)이 많음")
    if need_min > left:
        reasons.append(f"모든 팀을 2명 이상으로 채우려면 {need_min}명이 필요한데 팀이 없는 학생은 {left}명임")
    for t, ms in teams.items():
        mains = {m.main_role for m in ms}
        cand = [s for s in unassigned if s.main_role not in mains]
        for role in required_cover(ms):
            if role in (PL, WP) and not any(s.can(role) for s in cand):
                reasons.append(f"{t}에 {role}를 맡을 학생이 없음")
        miss = required_cover(ms)
        if len(miss) > MAX_SIZE - len(ms):
            reasons.append(f"{t}에 필수 포함 역할을 채울 자리가 모자람")
    if not reasons:
        reasons.append("모든 경우를 따져 봤지만 인원·주 역할 중복·필수 포함 역할을 함께 지키는 배정이 없음")
    return "; ".join(dict.fromkeys(reasons))
