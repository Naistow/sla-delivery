import logging
import time
from typing import Any, Callable, Dict, List, Optional
import requests
from .domain import DirectoryError

log = logging.getLogger(__name__)


class DirectoryClient:
    """Тонкий адаптер над requests для получения справочника зон доставки из 1С по HTTP."""

    def __init__(
        self,
        base_url: str,
        session: Optional[requests.Session] = None,
        timeout: float = 5.0,
        retries: int = 3,
        pause: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.retries = retries
        self.pause = pause
        self.sleep = sleep

    def zones(self) -> List[Dict[str, Any]]:
        url = self.base_url + "/zones/list"
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.HTTPError,
                ValueError,
            ) as exc:
                last_exc = exc
                log.warning("ошибка запроса к справочнику зон (%d/%d): %s", attempt, self.retries, exc)
                if attempt < self.retries:
                    self.sleep(self.pause * attempt)
        raise DirectoryError(f"справочник зон не ответил: {last_exc}")
