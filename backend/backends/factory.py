from __future__ import annotations

import os
from pathlib import Path

from backends.base import StoreBackend
from backends.memory_backend import MemoryBackend


def create_backend() -> StoreBackend:
    data_backend = os.getenv("DATA_BACKEND", "mysql").strip().lower()
    if data_backend == "mysql":
        from backends.mysql_backend import MySQLBackend
        from db.init_schema import init_schema
        from db.seed import seed_mysql_from_json

        init_schema()
        backend = MySQLBackend()
        should_seed = os.getenv("SEED_MYSQL_FROM_JSON_ON_EMPTY", "true").strip().lower() == "true"
        if should_seed and backend.is_empty():
            data_path = Path(__file__).resolve().parents[1] / "data" / "mysql.json"
            if data_path.exists():
                seed_mysql_from_json(data_path=data_path, truncate=False)
        return backend

    return MemoryBackend()
