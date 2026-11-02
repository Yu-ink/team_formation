"""Supabase 일시정지 막기: 매일 한 번 DB에 질의한다(GitHub Actions가 실행).

DATABASE_URL은 GitHub 저장소 Settings > Secrets and variables > Actions에 넣는다.
주소나 비밀번호는 출력하지 않는다.
"""
import os
import sys
from datetime import datetime, timezone

import psycopg

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL: 없음")
with psycopg.connect(url, prepare_threshold=None) as conn:
    n = conn.execute("select count(*) from tf_students").fetchone()[0]
    conn.execute(
        "insert into tf_settings(key, value) values ('last_keepalive', %s) "
        "on conflict (key) do update set value = excluded.value",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
    )
print(f"OK: tf_students {n}행, last_keepalive 갱신")
