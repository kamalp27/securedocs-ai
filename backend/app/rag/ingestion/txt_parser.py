"""Plaintext and Markdown document parser."""

import re
from pathlib import Path
from typing import List, Optional

from app.rag.ingestion.base import (
    BaseDocumentParser,
    EmptyDocumentError,
    ExtractedSegment,
    MalformedDocumentError,
    ParsedDocument,
)


class PlaintextParser(BaseDocumentParser):
    """Secure parser for TXT and Markdown files supporting multiple encodings."""

    ENCODINGS = ["utf-8", "utf-8-sig", "latin-1"]

    def parse(self, file_path: Path, document_title: Optional[str] = None) -> ParsedDocument:
        title = document_title or file_path.stem
        segments: List[ExtractedSegment] = []
        raw_text: Optional[str] = None

        with open(file_path, "rb") as f:
            raw_bytes = f.read()

        if not raw_bytes or not raw_bytes.strip():
            raise EmptyDocumentError("Plaintext document contains 0 bytes.")

        # Attempt decoding with supported encodings
        for encoding in self.ENCODINGS:
            try:
                raw_text = raw_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if raw_text is None:
            raise MalformedDocumentError(
                "Unable to decode text file using UTF-8 or Latin-1 encodings."
            )

        # Normalize line endings to standard Unix \n
        normalized_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

        # Split into distinct paragraphs (delimited by 2 or more newlines)
        paragraphs = re.split(r"\n{2,}", normalized_text)
        current_offset = 0

        for p in paragraphs:
            cleaned = p.strip()
            if not cleaned:
                continue

            seg_start = current_offset
            seg_end = current_offset + len(cleaned)

            segments.append(
                ExtractedSegment(
                    text=cleaned,
                    page_number=None,  # Plaintext does not have native page numbers
                    section=None,
                    start_char=seg_start,
                    end_char=seg_end,
                )
            )
            current_offset = seg_end + 2

        if not segments:
            raise EmptyDocumentError("Plaintext document contains no usable text.")

        total_chars = sum(len(s.text) for s in segments)
        return ParsedDocument(title=title, segments=segments, total_chars=total_chars)
