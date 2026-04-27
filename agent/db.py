from contextlib import contextmanager
from typing import Generator, Optional

from psycopg2 import pool
from psycopg2.extensions import connection

from agent.config import (
    DATABASE_URL,
    DB_CONNECT_TIMEOUT,
    DB_POOL_MAX_CONN,
    DB_POOL_MIN_CONN,
)

_connection_pool: Optional[pool.SimpleConnectionPool] = None


def _build_pool() -> pool.SimpleConnectionPool:
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it in your environment or .env file."
        )

    return pool.SimpleConnectionPool(
        minconn=DB_POOL_MIN_CONN,
        maxconn=DB_POOL_MAX_CONN,
        dsn=DATABASE_URL,
        connect_timeout=DB_CONNECT_TIMEOUT,
    )


def get_pool() -> pool.SimpleConnectionPool:
    global _connection_pool

    if _connection_pool is None:
        _connection_pool = _build_pool()

    return _connection_pool


@contextmanager
def get_connection() -> Generator[connection, None, None]:
    active_pool = get_pool()
    conn = active_pool.getconn()
    try:
        yield conn
    finally:
        active_pool.putconn(conn)


def close_pool() -> None:
    global _connection_pool

    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None
