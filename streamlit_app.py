"""팀 프로젝트를 위한 팀 편성 웹 앱 (Streamlit + Supabase + OpenRouter)

화면 요소의 key는 공고 2.7절 표를 그대로 따른다.
다른 사람의 변경 보기: st.fragment(run_every=5)로 바뀐 부분만 5초마다 저절로 다시 그린다(어려운 해결).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from tf import ai, config, rules, service
from tf.db import Database

st.set_page_config(page_title="팀 편성", page_icon="🧩", layout="wide")
KST = ZoneInfo("Asia/Seoul")
REFRESH_SEC = 5


# ============================================================ DB 준비(한 번만)
@st.cache_resource(show_spinner="DB에 연결하는 중…")
def get_db() -> Database:
    db = Database(config.get("DATABASE_URL"))
    db.apply_schema()
    service.ensure_admin(db, config.get("ADMIN_PASSWORD"))
    return db


if not config.get("DATABASE_URL") or not config.get("ADMIN_PASSWORD"):
    st.error(
        "설정이 비어 있음 — DATABASE_URL: " + config.has("DATABASE_URL")
        + ", ADMIN_PASSWORD: " + config.has("ADMIN_PASSWORD")
        + ". Streamlit Secrets(또는 .env)에 넣어 주세요."
    )
    st.stop()

try:
    db = get_db()
except Exception as e:  # 연결 주소는 화면에 내보내지 않는다
    st.error(f"DB에 연결하지 못함(오류 종류: {type(e).__name__}). Supabase 프로젝트가 일시정지되었는지 확인하세요.")
    st.stop()


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        return "막힘", f"DB 오류로 처리하지 못함. 다시 눌러 주세요(오류 종류: {type(e).__name__})"


def show_result(word_msg, empty_text="아직 누른 단추가 없음"):
    if not word_msg:
        st.caption(empty_text)
        return
    word, msg = word_msg
    text = f"{word}: {msg}"
    {"승인": st.success, "대기": st.info, "거절": st.error, "막힘": st.warning}.get(word, st.write)(text)


def now_kst():
    return datetime.now(KST).strftime("%H:%M:%S")


def subs_text(s):
    return ", ".join(s.sub_roles) if s.sub_roles else "없음"


def logout():
    for k in ("user_no", "result", "admin_result", "assign"):
        st.session_state.pop(k, None)


# ============================================================ 로그인 화면
def login_page():
    st.title("🧩 팀 프로젝트 팀 편성")
    st.caption("학번과 비밀번호로 로그인하세요. 관리자는 학번 admin")
    with st.form("login_form"):
        no = st.text_input("학번", key="login_student_no")
        pw = st.text_input("비밀번호", type="password", key="login_password")
        submitted = st.form_submit_button("로그인", key="login_submit", type="primary")
    if submitted:
        user = None
        try:
            user = service.login(db, no, pw)
        except Exception as e:
            st.session_state["login_error"] = f"DB 오류(오류 종류: {type(e).__name__})"
        if user:
            st.session_state["user_no"] = user["student_no"]
            st.session_state.pop("result", None)
            st.session_state.pop("login_error", None)
            st.rerun()
        else:
            st.session_state.setdefault("login_error", "학번 또는 비밀번호가 틀림")
    if st.session_state.get("login_error"):
        with st.container(key="result"):
            show_result(("막힘", st.session_state.pop("login_error")))


# ============================================================ 학생 화면
def student_page(user):
    with st.container(key="whoami"):
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"#### 👤 {user['name']} 님 (학번 {user['student_no']})")
        c2.button("로그아웃", key="logout", on_click=logout)
    student_board(user["student_no"])


def on_apply(user_no, team_no):
    st.session_state["result"] = safe(service.apply, db, user_no, team_no)


def on_vote(user_no, app_id, yes):
    st.session_state["result"] = safe(service.vote, db, user_no, app_id, yes)


@st.fragment(run_every=REFRESH_SEC)
def student_board(user_no):
    try:
        s = service.read_state(db)
    except Exception as e:
        st.warning(f"상태를 읽지 못함(오류 종류: {type(e).__name__}). 5초 뒤 다시 시도함")
        return
    me = s.by_no.get(user_no)
    if me is None:
        st.warning("명단이 새로 올라와 이 계정이 없어졌습니다. 다시 로그인하세요.")
        if st.button("다시 로그인", key="relogin"):
            logout()
            st.rerun(scope="app")
        return

    with st.container(key="result"):
        show_result(st.session_state.get("result"))

    my_team_id = s.team_of.get(me.id)
    pend = s.pending_of(me.id)
    st.markdown(f"**내 역할** · 주 역할 **{me.main_role}** / 보조 역할 {subs_text(me)}")
    if s.closed:
        st.info("모집이 마감됨 — 지원과 투표를 할 수 없음" + (" · 배정 확정됨" if s.confirmed else ""))
    if my_team_id:
        st.markdown(f"**내 팀** · {s.team(my_team_id).name}")
    else:
        st.markdown("**내 팀** · 아직 팀이 없음")
    if pend:
        st.markdown(f"**결과를 기다리는 지원** · {s.team(pend.team_id).name}")
    else:
        last = s.latest_app(me.id)
        if last and not my_team_id and last.status == "거절":
            st.caption(f"최근 지원: {s.team(last.team_id).name} 거절({last.reason or ''})")

    can_apply = not (my_team_id or pend or s.closed)
    st.subheader("팀 목록")
    cols = st.columns(2)
    for i, team in enumerate(s.teams):
        with cols[i % 2]:
            with st.container(key=f"team_{team.no}", border=True):
                mine = " · 🟢 내 팀" if team.id == my_team_id else ""
                st.markdown(f"##### {team.name} ({len(team.members)}/4명){mine}")
                if team.members:
                    for m in team.members:
                        st.markdown(f"- **{m.name}** — 주 {m.main_role} / 보조 {subs_text(m)}")
                else:
                    st.caption("빈 팀 — 지원하면 바로 승인")
                st.button(
                    f"{team.name}에 지원", key=f"apply_{team.no}", disabled=not can_apply,
                    on_click=on_apply, args=(user_no, team.no), width="stretch",
                )

    if my_team_id:
        st.subheader("내 팀에 들어온 지원")
        apps = s.pending_for_team(my_team_id)
        if not apps:
            st.caption("기다리는 지원 없음")
        team = s.team(my_team_id)
        for a in apps:
            ap = s.students[a.student_id]
            vs = s.votes.get(a.id, {})
            with st.container(border=True):
                st.markdown(f"**{ap.name}** — 주 {ap.main_role} / 보조 {subs_text(ap)}")
                st.caption("투표: " + ", ".join(f"{m.name} {vs.get(m.id, '아직')}" for m in team.members))
                if me.id in vs:
                    st.markdown(f"내 투표: **{vs[me.id]}**")
                else:
                    c1, c2 = st.columns(2)
                    c1.button("찬성", key=f"vote_yes_{ap.student_no}", on_click=on_vote,
                              args=(user_no, a.id, True), width="stretch", type="primary")
                    c2.button("거부", key=f"vote_no_{ap.student_no}", on_click=on_vote,
                              args=(user_no, a.id, False), width="stretch")
    st.caption(f"화면은 {REFRESH_SEC}초마다 저절로 바뀜 · 마지막 갱신 {now_kst()} (한국 시간)")


# ============================================================ 관리자 화면
def admin_page(user):
    with st.container(key="whoami"):
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"#### 🛠️ {user['name']} (admin)")
        c2.button("로그아웃", key="logout", on_click=logout)

    result_box = st.container(key="result")
    with result_box:
        result_slot = st.empty()
    with result_slot.container():
        show_result(st.session_state.get("admin_result"))

    left, right = st.columns([2, 3])
    with left:
        st.subheader("1. 명단 올리기")
        st.file_uploader("명단 CSV (UTF-8, BOM 있어도 됨)", type=["csv"], key="admin_roster_file")
        st.number_input("팀 수", min_value=1, max_value=20, value=4, step=1, key="admin_team_count")
        st.button("명단으로 처음 상태 만들기", key="admin_start", on_click=on_admin_start, type="primary")
        st.caption("지원·투표·팀원·마감 표시가 모두 지워지고 학생 비밀번호는 1234로 만들어짐")

        st.subheader("2. 모집 마감")
        st.button("모집 마감", key="admin_close", on_click=on_admin_close)

        st.subheader("3. AI 배정과 확정")
        clicked = st.button("AI 배정", key="admin_assign")
        status_box = st.container(key="assign_status", border=True)
        if clicked:
            run_assign(status_box, result_slot)
        else:
            with status_box:
                render_assign(st.session_state.get("assign"))
        st.button("배정안 확정", key="admin_confirm", on_click=on_admin_confirm, type="primary")

    with right:
        admin_board()


def is_admin():
    """관리자 기능은 서버에서 다시 확인한다(학생 계정으로 쓸 수 없게)."""
    no = st.session_state.get("user_no")
    try:
        u = service.get_user(db, no) if no else None
    except Exception:
        return False
    return bool(u and u["is_admin"])


def on_admin_start():
    if not is_admin():
        st.session_state["admin_result"] = ("막힘", "관리자만 쓸 수 있음")
        return
    f = st.session_state.get("admin_roster_file")
    data = f.getvalue() if f is not None else b""
    st.session_state["admin_result"] = safe(service.reset_roster, db, data, st.session_state.get("admin_team_count", 4))
    if st.session_state["admin_result"][0] == "승인":
        st.session_state.pop("assign", None)


def on_admin_close():
    if not is_admin():
        st.session_state["admin_result"] = ("막힘", "관리자만 쓸 수 있음")
        return
    st.session_state["admin_result"] = safe(service.close, db)


def on_admin_confirm():
    if not is_admin():
        st.session_state["admin_result"] = ("막힘", "관리자만 쓸 수 있음")
        return
    a = st.session_state.get("assign") or {}
    if a.get("confirmed"):
        st.session_state["admin_result"] = ("막힘", "이미 확정됨")
        return
    word, msg = safe(service.confirm, db, a.get("plan") if a.get("ok") else None)
    st.session_state["admin_result"] = (word, msg)
    if word == "승인":
        a["confirmed"] = True
        st.session_state["assign"] = a


def run_assign(status_box, result_slot):
    if not is_admin():
        st.session_state["admin_result"] = ("막힘", "관리자만 쓸 수 있음")
        return
    try:
        s, teams, unassigned = service.assignment_input(db)
    except Exception as e:
        word_msg = ("막힘", f"DB 오류(오류 종류: {type(e).__name__})")
        with result_slot.container():
            show_result(word_msg)
        st.session_state["admin_result"] = word_msg
        return
    if not s.teams:
        word_msg = ("막힘", "명단을 먼저 올리세요")
    elif not s.closed:
        word_msg = ("막힘", "모집을 먼저 마감하세요")
    elif s.confirmed:
        word_msg = ("막힘", "이미 확정됨")
    else:
        word_msg = None
    if word_msg:
        st.session_state["admin_result"] = word_msg
        with result_slot.container():
            show_result(word_msg)
        with status_box:
            render_assign(st.session_state.get("assign"))
        return

    with status_box:
        progress = st.empty()
        progress.info("배정 준비 중…")

        def on_progress(text):
            progress.info("⏳ " + text)

        out = ai.assign(teams, unassigned, on_progress=on_progress,
                        log=lambda *a: service.log_ai(db, *a))
        progress.empty()
        by_no = {x.student_no: x for x in unassigned}
        out["rows"] = [
            {"이름": by_no[no].name, "주 역할": by_no[no].main_role, "보조 역할": subs_text(by_no[no]), "배정된 팀": t}
            for no, t in (out["plan"] or [])
        ]
        st.session_state["assign"] = out
        render_assign(out)
    word_msg = ("승인", f"배정안을 만듦 — {out['source']}") if out["ok"] else ("막힘", out["message"])
    st.session_state["admin_result"] = word_msg
    with result_slot.container():
        show_result(word_msg)


def render_assign(a):
    if not a:
        st.caption("AI 배정 진행 안내가 여기에 보임(마감 뒤 'AI 배정'을 누르세요)")
        return
    if a.get("ok"):
        head = "확정됨 — " if a.get("confirmed") else "검사를 통과한 배정안 — "
        st.success(f"승인: {head}{a['message']}")
        if a.get("rows"):
            st.table(a["rows"])
        elif not a.get("confirmed"):
            st.caption("배정할 학생이 없음. '배정안 확정'을 누르면 확정됨")
    else:
        st.warning(a["message"])
    if a.get("attempts"):
        with st.expander("AI 호출 기록", expanded=not a.get("ok") or a.get("source", "").startswith("앱")):
            st.table(a["attempts"])


@st.fragment(run_every=REFRESH_SEC)
def admin_board():
    try:
        s = service.read_state(db)
    except Exception as e:
        st.warning(f"상태를 읽지 못함(오류 종류: {type(e).__name__})")
        return
    state = "마감" + (" · 확정됨" if s.confirmed else "") if s.closed else "모집 중"
    st.subheader(f"팀 현황 · {state}")
    if not s.teams:
        st.caption("명단을 올리면 팀이 만들어짐")
    cols = st.columns(2)
    for i, team in enumerate(s.teams):
        with cols[i % 2]:
            with st.container(key=f"team_{team.no}", border=True):
                errs = rules.final_team_errors({team.name: team.members}) if s.confirmed else []
                st.markdown(f"##### {team.name} ({len(team.members)}/4명)" + (" ⚠️" if errs else ""))
                if team.members:
                    for m in team.members:
                        st.markdown(f"- **{m.name}** — 주 {m.main_role} / 보조 {subs_text(m)}")
                else:
                    st.caption("빈 팀")
                for a in s.pending_for_team(team.id):
                    ap = s.students[a.student_id]
                    vs = s.votes.get(a.id, {})
                    st.caption(f"대기 중 지원: {ap.name} (찬성 {sum(v == '찬성' for v in vs.values())}/{len(team.members)})")

    st.subheader("팀이 없는 학생")
    with st.container(key="unassigned", border=True):
        un = s.unassigned()
        if un:
            for x in un:
                st.markdown(f"- **{x.name}** — 주 {x.main_role} / 보조 {subs_text(x)}")
        else:
            st.caption("팀이 없는 학생 없음")
    st.caption(f"{REFRESH_SEC}초마다 저절로 바뀜 · 마지막 갱신 {now_kst()} (한국 시간)")


# ============================================================ 시작
user_no = st.session_state.get("user_no")
user = None
if user_no:
    try:
        user = service.get_user(db, user_no)
    except Exception:
        user = None
    if user is None and user_no != service.ADMIN_NO:
        logout()

if not user:
    login_page()
elif user["is_admin"]:
    admin_page(user)
else:
    student_page(user)
