"""Document ingestion and parser module."""

from app.rag.ingestion.base import (
    BaseDocumentParser,
    DocumentParserError,
    EmptyDocumentError,
    EncryptedDocumentError,
    ExtractedSegment,
    MalformedDocumentError,
    ParsedDocument,
)
from app.rag.ingestion.docx_parser import DOCXParser
from app.rag.ingestion.parser_factory import get_parser_for_path
from app.rag.ingestion.pdf_parser import PDFParser
from app.rag.ingestion.txt_parser import PlaintextParser

__all__ = [
    "BaseDocumentParser",
    "DocumentParserError",
    "EncryptedDocumentError",
    "EmptyDocumentError",
    "MalformedDocumentError",
    "ExtractedSegment",
    "ParsedDocument",
    "PDFParser",
    "DOCXParser",
    "PlaintextParser",
    "get_parser_for_path",
]