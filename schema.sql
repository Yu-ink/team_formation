-- 팀 편성 웹 앱 DB 구조 (Supabase PostgreSQL)
-- 앱이 시작할 때 이 파일을 그대로 실행한다(이미 있으면 건너뜀). Supabase SQL 편집기에 붙여 넣어 실행해도 된다.
-- 모든 테이블 이름은 tf_ 로 시작한다.

-- 학생과 관리자. 비밀번호는 bcrypt 해시만 저장한다.
create table if not exists tf_students (
    id            bigint generated always as identity primary key,
    student_no    text    not null unique,                 -- 학번(유일). 관리자는 'admin'
    name          text    not null,
    main_role     text    check (main_role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    password_hash text    not null,                        -- bcrypt 해시
    is_admin      boolean not null default false,
    constraint tf_students_role_needed check (is_admin or main_role is not null)
);

-- 보조 역할(학생 1명에 0~2행). ord는 명단 CSV에 적힌 순서.
create table if not exists tf_student_sub_roles (
    student_id bigint   not null references tf_students(id) on delete cascade,
    role       text     not null check (role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    ord        smallint not null default 1 check (ord between 1 and 2),
    primary key (student_id, role)
);

-- 팀(팀1, 팀2, ...). team_no는 화면 key(team_1, apply_1)에 쓰는 번호.
create table if not exists tf_teams (
    id      bigint generated always as identity primary key,
    team_no int  not null unique check (team_no >= 1),
    name    text not null unique
);

-- 팀원. (team_id, slot_no) 기본 키: 같은 자리에 두 명이 동시에 들어가면 먼저 도착한 학생만 기록된다.
-- student_id 유일: 한 학생은 한 팀에만 속한다.
create table if not exists tf_members (
    team_id    bigint      not null references tf_teams(id) on delete cascade,
    slot_no    int         not null check (slot_no between 1 and 4),
    student_id bigint      not null unique references tf_students(id) on delete cascade,
    joined_at  timestamptz not null default now(),
    primary key (team_id, slot_no)
);

-- 지원. 거절 이유를 함께 남긴다.
create table if not exists tf_applications (
    id          bigint generated always as identity primary key,
    team_id     bigint      not null references tf_teams(id) on delete cascade,
    student_id  bigint      not null references tf_students(id) on delete cascade,
    status      text        not null check (status in ('대기', '승인', '거절')),
    reason      text,
    created_at  timestamptz not null default now(),
    decided_at  timestamptz
);
-- 한 학생은 결과를 기다리는 지원을 하나만 가질 수 있다(동시에 두 팀에 지원하는 경우도 DB가 막음).
create unique index if not exists tf_applications_one_pending
    on tf_applications (student_id) where status = '대기';

-- 투표. 한 번 투표하면 바꿀 수 없다(기본 키가 두 번째 투표를 막음).
create table if not exists tf_votes (
    application_id bigint      not null references tf_applications(id) on delete cascade,
    voter_id       bigint      not null references tf_students(id) on delete cascade,
    vote           text        not null check (vote in ('찬성', '거부')),
    created_at     timestamptz not null default now(),
    primary key (application_id, voter_id)
);

-- 설정: closed(모집 마감 여부), confirmed(배정 확정 여부), last_keepalive 등
create table if not exists tf_settings (
    key   text primary key,
    value text not null
);

-- AI 호출 기록(모델, 결과, 걸린 시간). 키는 기록하지 않는다.
create table if not exists tf_ai_logs (
    id         bigint generated always as identity primary key,
    created_at timestamptz not null default now(),
    attempt    int  not null,
    model      text not null,
    outcome    text not null,       -- 성공, 시간 초과, HTTP 429, 빈 응답, JSON 아님, 규칙 위반 ...
    elapsed_ms int,
    detail     text
);

-- Supabase Data API(익명 키)로 표를 읽거나 쓰지 못하게 막는다.
-- 앱은 테이블 주인(postgres) 계정으로 직접 연결하므로 영향이 없다.
alter table tf_students          enable row level security;
alter table tf_student_sub_roles enable row level security;
alter table tf_teams             enable row level security;
alter table tf_members           enable row level security;
alter table tf_applications      enable row level security;
alter table tf_votes             enable row level security;
alter table tf_settings          enable row level security;
alter table tf_ai_logs           enable row level security;
