import logging
import re
import time
from pathlib import Path
from . import config

log = logging.getLogger(__name__)


def connect(database: str = None, retries: int = 30, delay: float = 2.0):
    import pymssql

    target_db = config.DB_NAME if database is None else database
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            conn = pymssql.connect(
                server=config.DB_HOST,
                port=config.DB_PORT,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
                database=target_db,
                autocommit=True,
                charset="UTF-8",
            )
            return conn
        except Exception as exc:
            last_exc = exc
            log.warning(
                "попытка подключения к SQL Server (%s:%s/%s) %d/%d не удалась: %s",
                config.DB_HOST,
                config.DB_PORT,
                target_db,
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"не удалось подключиться к SQL Server после {retries} попыток: {last_exc}")


def run_init_script(sql_path: Path = Path("db/init.sql")) -> None:
    script = sql_path.read_text(encoding="utf-8")
    batches = [b.strip() for b in re.split(r"^\s*GO\s*$", script, flags=re.MULTILINE | re.IGNORECASE) if b.strip()]
    conn = connect(database="master")
    try:
        cur = conn.cursor()
        for batch in batches:
            cur.execute(batch)
        log.info("схема применена (%d пакетов SQL)", len(batches))
    finally:
        conn.close()
