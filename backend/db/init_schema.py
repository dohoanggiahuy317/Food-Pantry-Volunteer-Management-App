from __future__ import annotations

from pathlib import Path

import mysql.connector
from mysql.connector import errorcode, Error as MySQLError

from db.mysql import get_connection, mysql_config


def ensure_database_exists() -> None:
    db_name = str(mysql_config(include_database=True)["database"])
    admin_config = mysql_config(include_database=False)
    conn = mysql.connector.connect(**admin_config)
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            conn.commit()
        except mysql.connector.Error as exc:
            # In many environments (e.g. app-level DB user), CREATE DATABASE is not granted.
            # If privilege is missing, continue and let downstream connection verify DB exists.
            if exc.errno not in {errorcode.ER_DBACCESS_DENIED_ERROR, errorcode.ER_ACCESS_DENIED_ERROR}:
                raise
    finally:
        conn.close()


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    in_backtick = False
    in_line_comment = False
    in_block_comment = False

    i = 0
    length = len(sql)
    while i < length:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < length else ""
        prev = sql[i - 1] if i > 0 else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if not (in_single or in_double or in_backtick):
            if ch == "-" and nxt == "-":
                in_line_comment = True
                i += 2
                continue
            if ch == "#":
                in_line_comment = True
                i += 1
                continue
            if ch == "/" and nxt == "*":
                in_block_comment = True
                i += 2
                continue

        if ch == "'" and not (in_double or in_backtick) and prev != "\\":
            in_single = not in_single
        elif ch == '"' and not (in_single or in_backtick) and prev != "\\":
            in_double = not in_double
        elif ch == "`" and not (in_single or in_double):
            in_backtick = not in_backtick

        if ch == ";" and not (in_single or in_double or in_backtick):
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)

    return statements


def apply_sql(sql: str) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            try:
                for _ in cursor.execute(sql, multi=True):
                    pass
            except TypeError:
                # Some cursor implementations do not support `multi=True`.
                for statement in _split_sql_statements(sql):
                    cursor.execute(statement)
            conn.commit()
        except MySQLError:
            conn.rollback()
            raise


def init_schema() -> None:
    """Initialize schema idempotently using all SQL migrations in order."""
    ensure_database_exists()
    migrations_dir = Path(__file__).resolve().parent / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))
    for migration_file in migration_files:
        sql = migration_file.read_text(encoding="utf-8")
        apply_sql(sql)


if __name__ == "__main__":
    init_schema()
    print("Database schema initialized successfully")
