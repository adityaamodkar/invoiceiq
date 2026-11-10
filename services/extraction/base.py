"""Provider interface for structured invoice extraction."""
from __future__ import annotations

from abc import ABC, abstractmethod

from services.models import DocumentText, InvoiceDraft


class ExtractionProvider(ABC):
    name: str = "base"

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Return (available, human-readable status)."""

    @abstractmethod
    def extract(self, doc: DocumentText) -> InvoiceDraft:
        """Convert document text into an InvoiceDraft. Must not invent values."""
