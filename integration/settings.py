import os
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class Settings:
    db_host: str = "localhost"
    db_port: int = 1433
    db_name: str = "sla_delivery"
    db_user: str = "sa"
    db_password: str = ""
    directory_url: str = "http://localhost:8080"

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        src = os.environ if env is None else env
        return cls(
            db_host=src.get("DB_HOST", cls.db_host),
            db_port=int(src.get("DB_PORT", str(cls.db_port))),
            db_name=src.get("DB_NAME", cls.db_name),
            db_user=src.get("DB_USER", cls.db_user),
            db_password=src.get("DB_PASSWORD", cls.db_password),
            directory_url=src.get("DIRECTORY_URL", cls.directory_url),
        )
