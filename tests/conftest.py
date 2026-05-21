"""Shared pytest fixtures and configuration."""

from __future__ import annotations

from pathlib import Path

REAL_RECEIPT_PATH = (
    Path(__file__).parent
    / "data"
    / "ICA Kvantum Malmborgs Caroli 530,03 kr 2026-04-27.pdf"
)
