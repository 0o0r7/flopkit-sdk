"""Centralized, environment-overridable Technocore endpoint configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TechnocoreConfig:
    """Runtime settings for the Technocore HTTP API."""

    base_url: str = os.getenv("FLOPKIT_BASE_URL", "https://technocore.chat")
    timeout: float = float(os.getenv("FLOPKIT_TIMEOUT", "20"))
    retries: int = int(os.getenv("FLOPKIT_RETRIES", "3"))
