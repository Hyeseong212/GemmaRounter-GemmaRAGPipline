from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class FinalScoreSettings:
    api_host: str = os.getenv("FINAL_SCORE_API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("FINAL_SCORE_API_PORT", "8290"))
