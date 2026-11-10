"""
Optional LLM extraction provider.

Not wired to any vendor yet: the choice of provider (and whether to use a paid
or free tier) is pending the project owner's approval. Until then this provider
reports itself as unavailable and the pipeline uses rule-based extraction.
Any future implementation must return an InvoiceDraft whose values then pass
through the same deterministic normalization and validation as rule output.
"""
from __future__ import annotations

from config.settings import LLMConfig
from services.extraction.base import ExtractionProvider
from services.models import DocumentText, InvoiceDraft


class LLMProvider(ExtractionProvider):
    name = "llm"

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig()

    def is_available(self) -> tuple[bool, str]:
        if not self.config.is_configured:
            return False, "LLM extraction not configured (no provider/API key set)"
        return False, f"LLM provider '{self.config.provider}' is not implemented yet"

    def extract(self, doc: DocumentText) -> InvoiceDraft:  # pragma: no cover
        raise NotImplementedError("LLM extraction has not been enabled for this deployment.")
