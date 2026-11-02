"""앱이 하는 일(로그인, 명단, 지원, 투표, 마감, 확정). 화면과 무관하게 DB만 다룬다.

결과는 (첫 단어, 문장) 꼴로 돌려준다. 첫 단어는 '승인', '대기', '거절', '막힘' 가운데 하나.
지원·투표·승인은 그 팀 행을 잠근(SELECT … FOR UPDATE) 트랜잭션 안에서 처리하므로
같은 팀에 대한 동작은 한 번에 하나씩 차례로 처리된다.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from . import rules
from .db import Database, Tx, is_unique_violation
from .rules import Student
from .security import check_pw, hash_pw

STUDENT_PASSWORD = "1234"
ADMIN_NO = "admin"


# ======================================================================= 상태 읽기
@dataclass
class App:
    id: int
    team_id: int
    student_id: int
    status: str
    reason: str | None
    created_at: object


@dataclass
class Team:
    id: int
    no: int
    name: str
    members: list = field(default_factory=list)


@dataclass
class State:
    students: dict
    teams: list
    team_of: dict
    apps: list
    votes: dict
    closed: bool
    confirmed: bool

    @property
    def by_no(self):
        return {s.student_no: s for s in self.students.values()}

    def team(self, team_id):
        return next((t for t in self.teams if t.id == team_id), None)

    def team_by_no(self, no):
        return next((t for t in self.teams if t.no == no), None)

    def pending_of(self, student_id):
        return next((a for a in self.apps if a.student_id == student_id and a.status == "대기"), None)

    def latest_app(self, student_id):
        mine = [a for a in self.apps if a.student_id == student_id]
        return mine[-1] if mine else None

    def unassigned(self):
        return [s for s in sorted(self.students.values(), key=lambda s: s.student_no) if s.id not in self.team_of]

    def pending_for_team(self, team_id):
        return [a for a in self.apps if a.team_id == team_id and a.status == "대기"]

    def team_dict(self):
        return {t.name: list(t.members) for t in self.teams}


def load_state(t: Tx) -> State:
    settings = {r["key"]: r["value"] for r in t.all("select key, value from tf_settings")}
    rows = t.all(
        "select s.id, s.student_no, s.name, s.main_role from tf_students s "
        "where not s.is_admin order by s.student_no"
    )
    subs: dict = {}
    for r in t.all("select student_id, role from tf_student_sub_roles order by student_id, ord"):
        subs.setdefault(r["student_id"], []).append(r["role"])
    students = {
        r["id"]: Student(r["id"], r["student_no"], r["name"], r["main_role"], tuple(subs.get(r["id"], ())))
        for r in rows
    }
    teams = [Team(r["id"], r["team_no"], r["name"]) for r in t.all("select id, team_no, name from tf_teams order by team_no")]
    by_id = {tm.id: tm for tm in teams}
    team_of = {}
    for r in t.all("select team_id, slot_no, student_id from tf_members order by team_id, slot_no"):
        if r["student_id"] in students and r["team_id"] in by_id:
            by_id[r["team_id"]].members.append(students[r["student_id"]])
            team_of[r["student_id"]] = r["team_id"]
    apps = [
        App(r["id"], r["team_id"], r["student_id"], r["status"], r["reason"], r["created_at"])
        for r in t.all("select id, team_id, student_id, status, reason, created_at from tf_applications order by id")
    ]
    votes: dict = {}
    for r in t.all("select application_id, voter_id, vote from tf_votes"):
        votes.setdefault(r["application_id"], {})[r["voter_id"]] = r["vote"]
    return State(
        students, teams, team_of, apps, votes,
        settings.get("closed") == "1", settings.get("confirmed") == "1",
    )


def read_state(db: Database) -> State:
    with db.tx() as t:
        return load_state(t)


def _set(t: Tx, key, value):
    t.run(
        "insert into tf_settings(key, value) values (%s, %s) "
        "on conflict (key) do update set value = excluded.value",
        (key, value),
    )


# ======================================================================= 로그인
def ensure_admin(db: Database, admin_password: str):
    """앱이 시작할 때 관리자 계정을 만들거나 비밀번호를 갱신한다."""
    with db.tx() as t:
        row = t.one("select id, password_hash from tf_students where student_no = %s", (ADMIN_NO,))
        if row is None:
            t.run(
                "insert into tf_students(student_no, name, main_role, password_hash, is_admin) "
                "values (%s, %s, null, %s, true)",
                (ADMIN_NO, "관리자", hash_pw(admin_password)),
            )
        elif not check_pw(admin_password, row["password_hash"]):
            t.run("update tf_students set password_hash = %s, is_admin = true where id = %s",
                  (hash_pw(admin_password), row["id"]))


def login(db: Database, student_no: str, password: str):
    student_no = (student_no or "").strip()
    if not student_no or not password:
        return None
    with db.tx() as t:
        row = t.one(
            "select id, student_no, name, is_admin, password_hash from tf_students where student_no = %s",
            (student_no,),
        )
    if row is None or not check_pw(password, row["password_hash"]):
        return None
    return {"student_no": row["student_no"], "name": row["name"], "is_admin": bool(row["is_admin"])}


def get_user(db: Database, student_no: str):
    with db.tx() as t:
        row = t.one("select id, student_no, name, is_admin from tf_students where student_no = %s", (student_no,))
    return row


# ======================================================================= 명단 올리기
def parse_roster(data: bytes):
    """명단 CSV(UTF-8, BOM 있어도 됨)를 읽는다. (학생 목록, 오류 목록)."""
    errors = []
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["CSV가 UTF-8이 아님"]
    reader = csv.DictReader(io.StringIO(text))
    need = ["student_no", "name", "main_role", "sub_roles"]
    header = [h.strip() for h in (reader.fieldnames or [])]
    if header[:4] != need and not all(h in header for h in need):
        return [], [f"CSV 첫 줄이 {','.join(need)} 이어야 함"]
    reader.fieldnames = header
    out, seen = [], set()
    for i, row in enumerate(reader, start=2):
        no = (row.get("student_no") or "").strip()
        name = (row.get("name") or "").strip()
        main = (row.get("main_role") or "").strip()
        subs_raw = row.get("sub_roles") or ""
        subs = [s.strip() for s in subs_raw.split(";") if s.strip()]
        if not no and not name and not main:
            continue
        if not no or not name:
            errors.append(f"{i}행: 학번이나 이름이 비어 있음")
            continue
        if no == ADMIN_NO:
            errors.append(f"{i}행: 학번 admin은 쓸 수 없음")
        if no in seen:
            errors.append(f"{i}행: 학번 {no}이 두 번 나옴")
        seen.add(no)
        if main not in rules.ROLES:
            errors.append(f"{i}행: 주 역할 '{main}'은 6개 역할이 아님")
        bad = [s for s in subs if s not in rules.ROLES]
        if bad:
            errors.append(f"{i}행: 보조 역할 '{', '.join(bad)}'은 6개 역할이 아님")
        if len(subs) > 2:
            errors.append(f"{i}행: 보조 역할은 2개까지")
        subs = [s for s in dict.fromkeys(subs) if s != main]
        out.append((no, name, main, subs))
    if not out and not errors:
        errors.append("명단에 학생이 없음")
    return out, errors


def reset_roster(db: Database, data: bytes, team_count: int):
    if not data:
        return "막힘", "명단 CSV 파일을 먼저 고르세요"
    try:
        team_count = int(team_count)
    except (TypeError, ValueError):
        return "막힘", "팀 수가 숫자가 아님"
    if not 1 <= team_count <= 20:
        return "막힘", "팀 수는 1~20 사이여야 함"
    students, errors = parse_roster(data)
    if errors:
        return "막힘", "명단 오류: " + "; ".join(errors[:5])
    hashed = [hash_pw(STUDENT_PASSWORD) for _ in students]  # 학생마다 소금(salt)이 다른 해시
    with db.tx() as t:
        t.run("delete from tf_votes")
        t.run("delete from tf_applications")
        t.run("delete from tf_members")
        t.run("delete from tf_teams")
        t.run("delete from tf_students where not is_admin")
        t.run("delete from tf_settings where key in ('closed', 'confirmed')")
        _set(t, "closed", "0")
        _set(t, "confirmed", "0")
        for n in range(1, team_count + 1):
            t.run("insert into tf_teams(team_no, name) values (%s, %s)", (n, f"팀{n}"))
        for (no, name, main, subs), h in zip(students, hashed):
            sid = t.one(
                "insert into tf_students(student_no, name, main_role, password_hash, is_admin) "
                "values (%s, %s, %s, %s, false) returning id",
                (no, name, main, h),
            )["id"]
            for k, r in enumerate(subs[:2], start=1):
                t.run("insert into tf_student_sub_roles(student_id, role, ord) values (%s, %s, %s)", (sid, r, k))
    return "승인", f"명단 {len(students)}명, 팀 {team_count}개로 처음 상태를 만듦"


# ======================================================================= 지원
def apply(db: Database, student_no: str, team_no: int):
    try:
        with db.tx() as t:
            return _apply(t, student_no, int(team_no))
    except Exception as e:
        if is_unique_violation(e):
            return "막힘", "방금 다른 동작이 먼저 처리됨(자리가 찼거나 이미 기다리는 지원이 있음). 화면을 보고 다시 시도하세요"
        raise


def _apply(t: Tx, student_no, team_no):
    team_row = t.one("select id, name from tf_teams where team_no = %s for update", (team_no,))
    if team_row is None:
        return "막힘", "없는 팀"
    s = load_state(t)
    me = s.by_no.get(student_no)
    if me is None:
        return "막힘", "명단에 없는 학생"
    team = s.team(team_row["id"])
    if s.closed:
        return "막힘", "모집이 마감됨"
    if me.id in s.team_of:
        return "막힘", "이미 팀이 있음"
    pend = s.pending_of(me.id)
    if pend:
        return "막힘", f"결과를 기다리는 지원이 있음({s.team(pend.team_id).name})"
    reason = rules.join_block_reason(team.members, me)
    if reason:
        return "막힘", reason
    if not team.members:  # 빈 팀: 투표할 팀원이 없으므로 바로 승인
        app_id = t.one(
            "insert into tf_applications(team_id, student_id, status, reason, decided_at) "
            "values (%s, %s, '승인', '빈 팀', now()) returning id",
            (team.id, me.id),
        )["id"]
        _add_member(t, team, me)
        return "승인", f"{team.name}에 들어감(빈 팀이라 바로 승인)"
    t.run(
        "insert into tf_applications(team_id, student_id, status) values (%s, %s, '대기')",
        (team.id, me.id),
    )
    return "대기", f"{team.name}에 지원함. 팀원 {len(team.members)}명의 투표를 기다림"


def _add_member(t: Tx, team: Team, student: Student):
    used = {r["slot_no"] for r in t.all("select slot_no from tf_members where team_id = %s", (team.id,))}
    free = [n for n in range(1, rules.MAX_SIZE + 1) if n not in used]
    if not free:
        raise RuntimeError("자리가 없음")
    # (team_id, slot_no) 기본 키와 student_id 유일 제약이 동시에 들어오는 두 번째 학생을 막는다
    t.run("insert into tf_members(team_id, slot_no, student_id) values (%s, %s, %s)", (team.id, free[0], student.id))


# ======================================================================= 투표
def vote(db: Database, voter_no: str, app_id: int, yes: bool):
    try:
        with db.tx() as t:
            return _vote(t, voter_no, int(app_id), yes)
    except Exception as e:
        if is_unique_violation(e):
            return "막힘", "이미 투표했거나 자리가 방금 찼음. 화면을 보고 확인하세요"
        raise


def _vote(t: Tx, voter_no, app_id, yes):
    row = t.one("select team_id from tf_applications where id = %s", (app_id,))
    if row is None:
        return "막힘", "없는 지원"
    t.one("select id from tf_teams where id = %s for update", (row["team_id"],))
    s = load_state(t)
    app = next((a for a in s.apps if a.id == app_id), None)
    voter = s.by_no.get(voter_no)
    team = s.team(app.team_id)
    applicant = s.students[app.student_id]
    who = applicant.name
    if voter is None or s.team_of.get(voter.id) != team.id:
        return "막힘", "이 팀의 팀원만 투표할 수 있음"
    if app.status != "대기":
        return app.status, f"{who}의 지원은 이미 {app.status}됨" + (f"({app.reason})" if app.reason else "")
    if s.closed:
        return "막힘", "모집이 마감됨"
    if voter.id in s.votes.get(app.id, {}):
        return "막힘", "이미 투표함(한 번 투표하면 바꿀 수 없음)"
    t.run("insert into tf_votes(application_id, voter_id, vote) values (%s, %s, %s)",
          (app.id, voter.id, "찬성" if yes else "거부"))
    if not yes:
        _decide(t, app.id, "거절", f"{voter.name}이(가) 거부")
        return "거절", f"{who}의 지원이 거절됨({voter.name}이(가) 거부)"
    voted = dict(s.votes.get(app.id, {}))
    voted[voter.id] = "찬성"
    left = [m for m in team.members if voted.get(m.id) != "찬성"]
    if left:
        return "대기", f"{who}의 지원: 남은 투표 {len(left)}명({', '.join(m.name for m in left)})"
    # 모든 팀원이 찬성 → 승인 직전에 규칙을 다시 검사(같은 팀에 대기 중인 지원이 여럿일 때)
    if applicant.id in s.team_of:
        _decide(t, app.id, "거절", "승인 직전 검사: 이미 팀이 있음")
        return "거절", f"{who}의 지원이 거절됨(승인 직전 검사: 이미 팀이 있음)"
    reason = rules.join_block_reason(team.members, applicant)
    if reason:
        _decide(t, app.id, "거절", f"승인 직전 검사: {reason}")
        return "거절", f"{who}의 지원이 거절됨(승인 직전 검사: {reason})"
    _add_member(t, team, applicant)
    _decide(t, app.id, "승인", "팀원 모두 찬성")
    return "승인", f"{who}의 지원이 승인됨. {team.name}의 팀원이 됨"


def _decide(t: Tx, app_id, status, reason):
    t.run("update tf_applications set status = %s, reason = %s, decided_at = now() where id = %s",
          (status, reason, app_id))


# ======================================================================= 마감
def close(db: Database):
    with db.tx() as t:
        t.all("select id from tf_teams order by id for update")
        s = load_state(t)
        if not s.teams:
            return "막힘", "명단을 먼저 올리세요"
        if s.closed:
            return "막힘", "이미 마감됨"
        n_rej = t.run(
            "update tf_applications set status = '거절', reason = '모집 마감', decided_at = now() where status = '대기'"
        )
        alone = [tm for tm in s.teams if len(tm.members) == 1]
        for tm in alone:
            t.run("delete from tf_members where team_id = %s", (tm.id,))
        _set(t, "closed", "1")
    names = ", ".join(tm.members[0].name for tm in alone) or "없음"
    return "승인", f"모집을 마감함. 대기 중인 지원 {n_rej}건 거절, 1명뿐인 팀에서 빠진 학생: {names}"


# ======================================================================= 배정 확정
def assignment_input(db: Database):
    """배정에 쓰는 (상태, 팀 구성, 팀이 없는 학생)."""
    s = read_state(db)
    return s, s.team_dict(), s.unassigned()


def confirm(db: Database, plan):
    if not plan:
        return "막힘", "확정할 배정안이 없음(먼저 AI 배정을 누르세요)"
    with db.tx() as t:
        t.all("select id from tf_teams order by id for update")
        s = load_state(t)
        if not s.closed:
            return "막힘", "모집을 먼저 마감하세요"
        if s.confirmed:
            return "막힘", "이미 확정됨"
        errors = rules.validate_plan(s.team_dict(), s.unassigned(), plan)
        if errors:
            return "막힘", "배정안이 지금 상태와 맞지 않음: " + "; ".join(errors[:3])
        by_name = {tm.name: tm for tm in s.teams}
        by_no = s.by_no
        for no, team_name in plan:
            tm = by_name[team_name]
            _add_member(t, tm, by_no[str(no)])
            tm.members.append(by_no[str(no)])
        _set(t, "confirmed", "1")
    return "승인", f"배정안을 확정함({len(plan)}명 배정)"


def log_ai(db: Database, attempt: int, model: str, outcome: str, elapsed_ms: int | None, detail: str = ""):
    try:
        with db.tx() as t:
            t.run(
                "insert into tf_ai_logs(attempt, model, outcome, elapsed_ms, detail) values (%s, %s, %s, %s, %s)",
                (attempt, model, outcome, elapsed_ms, (detail or "")[:500]),
            )
    except Exception:
        pass
