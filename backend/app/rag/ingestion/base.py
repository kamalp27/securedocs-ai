"""Base classes and structured data types for document parsing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


class DocumentParserError(Exception):
    """Base exception for document parsing failures."""
    pass


class EncryptedDocumentError(DocumentParserError):
    """Raised when an encrypted or password-protected document is encountered."""
    pass


class EmptyDocumentError(DocumentParserError):
    """Raised when no usable text can be extracted from the document."""
    pass


class MalformedDocumentError(DocumentParserError):
    """Raised when a document is structurally invalid or unreadable."""
    pass


@dataclass
class ExtractedSegment:
    """A discrete extracted text segment with source attribution."""
    text: str
    page_number: Optional[int] = None  # 1-based index (PDF only, None for DOCX/TXT)
    section: Optional[str] = None      # Header or section name where available
    start_char: int = 0               # Character offset within extracted document
    end_char: int = 0                 # Ending character offset


@dataclass
class ParsedDocument:
    """Complete structured representation of an extracted document."""
    title: str
    segments: List[ExtractedSegment]
    total_chars: int

    @property
    def full_text(self) -> str:
        """Concatenated full text across all segments."""
        return "\n\n".join(seg.text for seg in self.segments if seg.text.strip())


class BaseDocumentParser(ABC):
    """Abstract base class for format-specific document parsers."""

    @abstractmethod
    def parse(self, file_path: Path, document_title: Optional[str] = None) -> ParsedDocument:
        """Parse file from disk and return structured ParsedDocument."""
        pass
