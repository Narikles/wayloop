"""Erreur métier commune (séparée pour éviter les imports circulaires)."""
from __future__ import annotations

from typing import Any


class FlowError(Exception):
    """Erreur affichée telle quelle au dirigeant ; `extra` est renvoyé avec (ex. problèmes par champ)."""

    def __init__(self, message: str, status: int = 400, extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra or {}
