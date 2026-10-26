"""Public source-aligned chunking API, compatible with the former chunking.py."""
from .core import (
    Budget, CHUNKING_VERSION, Document, EXCEPTION, EXPLICIT, HEADING, NEGATIVE,
    PARSER_VERSION, PREFERRED, SECTION_NAMES, STRATEGIES, Section,
    build_documents, condition_level, item_spans, parse_sections,
)

__all__ = ["Budget", "CHUNKING_VERSION", "Document", "EXCEPTION", "EXPLICIT", "HEADING",
           "NEGATIVE", "PARSER_VERSION", "PREFERRED", "SECTION_NAMES", "STRATEGIES", "Section",
           "build_documents", "condition_level", "item_spans", "parse_sections"]
