from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPT_PATH = PROJECT_ROOT / "prompts" / "server_router_system_prompt.txt"
DEFAULT_ANSWER_PROMPT_PATH = PROJECT_ROOT / "prompts" / "server_answer_system_prompt.txt"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class ServerRouterSettings:
    model_endpoint: str = field(
        default_factory=lambda: os.getenv(
            "SERVER_ROUTER_MODEL_ENDPOINT",
            "http://127.0.0.1:8180/v1/chat/completions",
        )
    )
    model_name: str = field(
        default_factory=lambda: os.getenv("SERVER_ROUTER_MODEL_NAME", "gemma4-server-router")
    )
    prompt_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("SERVER_ROUTER_PROMPT_PATH", str(DEFAULT_PROMPT_PATH))
        )
    )
    answer_prompt_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("SERVER_ANSWER_PROMPT_PATH", str(DEFAULT_ANSWER_PROMPT_PATH))
        )
    )
    request_timeout: float = field(
        default_factory=lambda: float(os.getenv("SERVER_ROUTER_REQUEST_TIMEOUT", "30.0"))
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("SERVER_ROUTER_TEMPERATURE", "0.1"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("SERVER_ROUTER_MAX_TOKENS", "160"))
    )
    reasoning_mode: str = field(
        default_factory=lambda: os.getenv("SERVER_ROUTER_REASONING_MODE", "off")
    )
    reasoning_budget: int = field(
        default_factory=lambda: int(os.getenv("SERVER_ROUTER_REASONING_BUDGET", "0"))
    )
    answer_model_endpoint: str = field(
        default_factory=lambda: os.getenv(
            "SERVER_ANSWER_MODEL_ENDPOINT",
            os.getenv(
                "SERVER_ROUTER_MODEL_ENDPOINT",
                "http://127.0.0.1:8180/v1/chat/completions",
            ),
        )
    )
    answer_model_name: str = field(
        default_factory=lambda: os.getenv("SERVER_ANSWER_MODEL_NAME", "gemma4-server-answer")
    )
    answer_temperature: float = field(
        default_factory=lambda: float(os.getenv("SERVER_ANSWER_TEMPERATURE", "0.2"))
    )
    answer_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("SERVER_ANSWER_MAX_TOKENS", "400"))
    )
    rag_api_endpoint: str = field(
        default_factory=lambda: os.getenv(
            "SERVER_RAG_API_ENDPOINT",
            "http://127.0.0.1:8000/ask",
        )
    )
    final_score_endpoint: str = field(
        default_factory=lambda: os.getenv(
            "FINAL_SCORE_ENDPOINT",
            "http://127.0.0.1:8290/score/debug",
        )
    )
    api_host: str = field(
        default_factory=lambda: os.getenv("SERVER_ROUTER_API_HOST", "0.0.0.0")
    )
    api_port: int = field(
        default_factory=lambda: int(os.getenv("SERVER_ROUTER_API_PORT", "8190"))
    )


def load_project_env(env_path: Path = DEFAULT_ENV_PATH) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))
