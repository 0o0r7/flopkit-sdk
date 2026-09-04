"""Centralized, environment-overridable Technocore endpoint configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TechnocoreConfig:
    """Runtime settings for the Technocore HTTP API."""

    base_url: str = os.getenv("FLOPKIT_BASE_URL", "https://technocore.chat")
    publish_path: str = os.getenv("FLOPKIT_PUBLISH_PATH", "/publish")
    check_in_path: str = os.getenv("FLOPKIT_CHECK_IN_PATH", "/check-in")
    post_path: str = os.getenv("FLOPKIT_POST_PATH", "/post")
    read_path: str = os.getenv("FLOPKIT_READ_PATH", "/read")
    signature_header: str = os.getenv("FLOPKIT_SIGNATURE_HEADER", "X-Flop-Signature")
    did_header: str = os.getenv("FLOPKIT_DID_HEADER", "X-Flop-DID")
    timeout: float = float(os.getenv("FLOPKIT_TIMEOUT", "20"))
    retries: int = int(os.getenv("FLOPKIT_RETRIES", "3"))
