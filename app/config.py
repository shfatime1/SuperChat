"""Local configuration. The competition clock never follows the host clock."""

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DATE = date(2026, 11, 2)


@dataclass(frozen=True)
class Settings:
    api_key: str | None = field(default=None, repr=False)
    model: str = "gemini-flash-latest"
    data_dir: Path = PROJECT_ROOT / "data"
    routing_mode: str = "auto"
    gemini_timeout_ms: int = 8000
    response_timeout_ms: int = 4000
    secure_cookies: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        return cls(
            api_key=os.getenv("GEMINI_API_KEY") or None,
            model=os.getenv("GEMINI_MODEL") or "gemini-flash-latest",
            routing_mode=os.getenv("SUPERCHAT_ROUTING_MODE", "auto").lower(),
            gemini_timeout_ms=int(os.getenv("GEMINI_TIMEOUT_MS", "8000")),
            response_timeout_ms=int(os.getenv("GEMINI_RESPONSE_TIMEOUT_MS", "4000")),
            secure_cookies=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        )
