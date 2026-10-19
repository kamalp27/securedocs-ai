"""PDF Document Parser using pypdf."""

import re
from pathlib import Path
from typing import List, Optional

import pypdf
from pypdf.errors import PdfReadError

from app.rag.ingestion.base import (
    BaseDocumentParser,
    EmptyDocumentError,
    EncryptedDocumentError,
    ExtractedSegment,
    MalformedDocumentError,
    ParsedDocument,
)


class PDFParser(BaseDocumentParser):
    """Secure PDF text parser extracting per-page segments with 1-based indexing."""

    def parse(self, file_path: Path, document_title: Optional[str] = None) -> ParsedDocument:
        title = document_title or file_path.stem
        segments: List[ExtractedSegment] = []
        current_offset = 0

        try:
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)

                # Reject encrypted/password-protected PDFs strictly
                if reader.is_encrypted:
                    raise EncryptedDocumentError(
                        "Encrypted or password-protected PDF files are not supported."
                    )

                num_pages = len(reader.pages)
                if num_pages == 0:
                    raise EmptyDocumentError("PDF document contains no pages.")

                for idx, page in enumerate(reader.pages):
                    page_num = idx + 1  # 1-based indexing
                    raw_text = page.extract_text() or ""

                    # Normalize whitespace while preserving paragraphs
                    cleaned_text = re.sub(r"[ \t]+", " ", raw_text)
                    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()

                    if cleaned_text:
                        seg_start = current_offset
                        seg_end = current_offset + len(cleaned_text)
                        segments.append(
                            ExtractedSegment(
                                text=cleaned_text,
                                page_number=page_num,
                                section=f"Page {page_num}",
                                start_char=seg_start,
                                end_char=seg_end,
                            )
                        )
                        current_offset = seg_end + 2  # accounted for joining double newlines

        except (EncryptedDocumentError, EmptyDocumentError):
            raise
        except PdfReadError as e:
            raise MalformedDocumentError(f"Corrupt or malformed PDF file: {e}") from e
        except Exception as e:
            raise MalformedDocumentError(f"Failed to parse PDF document: {e}") from e

        if not segments:
            raise EmptyDocumentError(
                "PDF parsing completed, but no readable text could be extracted."
            )

        total_chars = sum(len(s.text) for s in segments)
        return ParsedDocument(title=title, segments=segments, total_chars=total_chars)
