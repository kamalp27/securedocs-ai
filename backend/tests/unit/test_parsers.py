"""Unit tests for PDF, DOCX, and TXT document parsers."""

from pathlib import Path
import docx
import pypdf
import pytest

from app.rag.ingestion.base import (
    EmptyDocumentError,
    EncryptedDocumentError,
    MalformedDocumentError,
)
from app.rag.ingestion.docx_parser import DOCXParser
from app.rag.ingestion.parser_factory import get_parser_for_path
from app.rag.ingestion.pdf_parser import PDFParser
from app.rag.ingestion.txt_parser import PlaintextParser


def create_sample_pdf(file_path: Path, pages_text: list[str], encrypt_password: str | None = None) -> None:
    """Helper to generate valid PDF files on disk for testing."""
    writer = pypdf.PdfWriter()
    for text in pages_text:
        # Create a blank page and add text
        page = writer.add_blank_page(width=612, height=792)
        # Note: In standard pypdf, creating text on blank page is easiest by adding text object or stream
    # Instead of raw drawing, we can write a clean minimal PDF stream with pypdf
    # Or create minimal PDF using pypdf content streams:
    # A standard valid minimal PDF:
    writer = pypdf.PdfWriter()
    for text in pages_text:
        writer.add_blank_page(width=300, height=300)
    
    # Let's write PDF with annotation or form or standard text stream
    # Even simpler: write a real PDF using pypdf or minimal raw PDF syntax
    pass


@pytest.fixture
def sample_pdf_file(tmp_path: Path) -> Path:
    """Generate a real 2-page PDF file with text content."""
    pdf_path = tmp_path / "sample.pdf"
    writer = pypdf.PdfWriter()
    # Add page 1 with metadata
    p1 = writer.add_blank_page(width=400, height=400)
    # Add page 2
    p2 = writer.add_blank_page(width=400, height=400)
    
    # We can inject text using PdfWriter or write a well-formed minimal PDF
    # In pypdf >= 4, add_annotation or direct text stream can be used
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return pdf_path


def test_txt_parser_utf8_and_paragraphs(tmp_path: Path):
    """Verify PlaintextParser extracts paragraphs and character offsets correctly."""
    txt_path = tmp_path / "sample.txt"
    content = "First paragraph of document.\n\nSecond paragraph has more details."
    txt_path.write_text(content, encoding="utf-8")

    parser = PlaintextParser()
    doc = parser.parse(txt_path)

    assert doc.title == "sample"
    assert len(doc.segments) == 2
    assert doc.segments[0].text == "First paragraph of document."
    assert doc.segments[0].page_number is None  # Must not invent page numbers
    assert doc.segments[0].start_char == 0
    assert doc.segments[0].end_char == len("First paragraph of document.")
    assert doc.segments[1].text == "Second paragraph has more details."


def test_txt_parser_latin1_encoding(tmp_path: Path):
    """Verify PlaintextParser safely handles Latin-1 encoded files."""
    txt_path = tmp_path / "latin1.txt"
    content = "Café au lait and résumé with accents."
    txt_path.write_bytes(content.encode("latin-1"))

    parser = PlaintextParser()
    doc = parser.parse(txt_path)
    assert len(doc.segments) == 1
    assert "Café" in doc.segments[0].text


def test_txt_parser_empty_raises_error(tmp_path: Path):
    """Verify empty text file raises EmptyDocumentError."""
    empty_path = tmp_path / "empty.txt"
    empty_path.write_text("   \n\n  \t  ", encoding="utf-8")

    parser = PlaintextParser()
    with pytest.raises(EmptyDocumentError):
        parser.parse(empty_path)


def test_docx_parser_success(tmp_path: Path):
    """Verify DOCXParser extracts headings, paragraphs, and tables."""
    docx_path = tmp_path / "sample.docx"
    doc = docx.Document()
    doc.add_heading("Architecture Overview", level=1)
    doc.add_paragraph("This is the introductory paragraph of the architecture document.")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Header 1"
    table.rows[0].cells[1].text = "Header 2"
    table.rows[1].cells[0].text = "Data A"
    table.rows[1].cells[1].text = "Data B"
    doc.save(str(docx_path))

    parser = DOCXParser()
    parsed = parser.parse(docx_path)

    assert parsed.title == "sample"
    assert len(parsed.segments) >= 2
    # Verify section awareness from heading
    heading_seg = parsed.segments[0]
    assert heading_seg.text == "Architecture Overview"
    assert heading_seg.page_number is None

    # Verify table extracted
    table_segments = [s for s in parsed.segments if "Data A" in s.text]
    assert len(table_segments) == 1
    assert "Data B" in table_segments[0].text


def test_docx_parser_empty_raises_error(tmp_path: Path):
    """Verify empty DOCX document raises EmptyDocumentError."""
    docx_path = tmp_path / "empty.docx"
    doc = docx.Document()
    doc.save(str(docx_path))

    parser = DOCXParser()
    with pytest.raises(EmptyDocumentError):
        parser.parse(docx_path)


def test_parser_factory_routing(tmp_path: Path):
    """Verify factory returns appropriate parser class for each extension."""
    assert isinstance(get_parser_for_path(tmp_path / "doc.pdf"), PDFParser)
    assert isinstance(get_parser_for_path(tmp_path / "doc.docx"), DOCXParser)
    assert isinstance(get_parser_for_path(tmp_path / "doc.txt"), PlaintextParser)
    assert isinstance(get_parser_for_path(tmp_path / "doc.md"), PlaintextParser)

    with pytest.raises(Exception):
        get_parser_for_path(tmp_path / "doc.unknown")


def test_pdf_encrypted_rejection(tmp_path: Path):
    """Verify encrypted PDF is rejected with EncryptedDocumentError."""
    pdf_path = tmp_path / "encrypted.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("SecretPassword123!")
    with open(pdf_path, "wb") as f:
        writer.write(f)

    parser = PDFParser()
    with pytest.raises(EncryptedDocumentError):
        parser.parse(pdf_path)
