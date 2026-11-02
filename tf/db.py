"""DB 연결. 연결 풀을 한 번만 만들고 계속 다시 쓴다(공고 4.2절).

Supabase는 'Session pooler' 주소(…pooler.supabase.com)를 DATABASE_URL로 쓴다.
Streamlit Community Cloud는 IPv6 직접 주소(db.xxx.supabase.co)에 닿지 못할 수 있다.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


class Tx:
    """트랜잭션 하나. 행은 dict로 돌려준다."""

    def __init__(self, conn):
        self.conn = conn

    def all(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        return list(cur.fetchall()) if cur.description else []

    def one(self, sql, params=()):
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def run(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        return cur.rowcount


class Database:
    def __init__(self, url: str):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(
            url,
            min_size=1,
            max_size=5,
            max_idle=300,
            kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row},
            check=ConnectionPool.check_connection,
            open=True,
        )

    @contextmanager
    def tx(self):
        with self.pool.connection() as conn:
            with conn.transaction():
                yield Tx(conn)

    def apply_schema(self):
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.pool.connection() as conn:
            conn.execute(sql)


def is_unique_violation(e: Exception) -> bool:
    return getattr(e, "sqlstate", None) == "23505"
