"""Parser factory routing files to appropriate parsers based on extension."""

from pathlib import Path
from typing import Dict, Type

from app.rag.ingestion.base import BaseDocumentParser, DocumentParserError
from app.rag.ingestion.docx_parser import DOCXParser
from app.rag.ingestion.pdf_parser import PDFParser
from app.rag.ingestion.txt_parser import PlaintextParser

PARSER_REGISTRY: Dict[str, Type[BaseDocumentParser]] = {
    ".pdf": PDFParser,
    ".docx": DOCXParser,
    ".txt": PlaintextParser,
    ".md": PlaintextParser,
}


def get_parser_for_path(file_path: Path) -> BaseDocumentParser:
    """Return an instantiated parser suitable for the target file extension."""
    ext = file_path.suffix.lower()
    parser_cls = PARSER_REGISTRY.get(ext)
    if not parser_cls:
        raise DocumentParserError(
            f"No registered document parser for file extension '{ext}'."
        )
    return parser_cls()
