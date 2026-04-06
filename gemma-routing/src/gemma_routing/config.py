from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPT_PATH = PROJECT_ROOT / "prompts" / "medical_router_system_prompt.txt"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class RouterSettings:
    model_endpoint: str = field(
        default_factory=lambda: os.getenv(
            "ROUTER_MODEL_ENDPOINT",
            "http://127.0.0.1:8080/v1/chat/completions",
        )
    )
    model_name: str = field(default_factory=lambda: os.getenv("ROUTER_MODEL_NAME", "gemma4-routing"))
    prompt_path: Path = field(
        default_factory=lambda: Path(os.getenv("ROUTER_PROMPT_PATH", str(DEFAULT_PROMPT_PATH)))
    )
    request_timeout: float = field(
        default_factory=lambda: float(os.getenv("ROUTER_REQUEST_TIMEOUT", "20.0"))
    )
    temperature: float = field(default_factory=lambda: float(os.getenv("ROUTER_TEMPERATURE", "0.2")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("ROUTER_MAX_TOKENS", "96")))
    reasoning_mode: str = field(default_factory=lambda: os.getenv("ROUTER_REASONING_MODE", "off"))
    reasoning_budget: int = field(default_factory=lambda: int(os.getenv("ROUTER_REASONING_BUDGET", "0")))
    api_host: str = field(default_factory=lambda: os.getenv("ROUTER_API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: int(os.getenv("ROUTER_API_PORT", "8090")))


def load_project_env(env_path: Path = DEFAULT_ENV_PATH) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))
