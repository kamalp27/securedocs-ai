"""Unit tests for upload validator: signature inspection, path sanitization, and size limits."""

import io
from pathlib import Path
import pytest
from fastapi import UploadFile

from app.services.upload_validator import (
    EmptyFileError,
    MalformedFileError,
    PathTraversalError,
    PayloadTooLargeError,
    UnsupportedFormatError,
    inspect_file_signatures,
    sanitize_filename,
    save_upload_safely,
)


def test_sanitize_filename_directory_traversal():
    """Verify that path traversal attempts are stripped from filename."""
    assert sanitize_filename("../../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"
    assert sanitize_filename("/var/log/app.log") == "app.log"
    assert sanitize_filename("C:\\Users\\Secret\\doc.pdf") == "doc.pdf"


def test_sanitize_filename_special_characters():
    """Verify special control characters and spaces are sanitized safely."""
    assert sanitize_filename("my document (1) [final].pdf") == "my document (1) [final].pdf"
    assert sanitize_filename("bad\x00name\x1fname.txt") == "badnamename.txt"
    assert sanitize_filename("   ") == "unnamed_document.txt"
    assert sanitize_filename("") == "unnamed_document.txt"


def test_inspect_file_signatures_pdf():
    """Verify PDF magic bytes validation."""
    valid_pdf_header = b"%PDF-1.5\n%Header info"
    stream = io.BytesIO(valid_pdf_header)
    mime = inspect_file_signatures(valid_pdf_header, ".pdf", stream)
    assert mime == "application/pdf"

    # Spoofed PDF (plain text claiming to be PDF)
    fake_header = b"This is not a PDF file at all"
    with pytest.raises(UnsupportedFormatError):
        inspect_file_signatures(fake_header, ".pdf", io.BytesIO(fake_header))


def test_inspect_file_signatures_empty():
    """Verify empty header raises EmptyFileError."""
    with pytest.raises(EmptyFileError):
        inspect_file_signatures(b"", ".txt", io.BytesIO(b""))


def test_inspect_file_signatures_unsupported_ext():
    """Verify unsupported extensions are rejected."""
    with pytest.raises(UnsupportedFormatError):
        inspect_file_signatures(b"MZ\x90\x00executable", ".exe", io.BytesIO(b"MZ"))


def test_inspect_file_signatures_txt_binary_nulls():
    """Verify binary null bytes in txt file are rejected."""
    binary_content = b"Some text with \x00 binary null byte"
    with pytest.raises(UnsupportedFormatError):
        inspect_file_signatures(binary_content, ".txt", io.BytesIO(binary_content))


def test_save_upload_safely_payload_too_large(tmp_path: Path):
    """Verify that oversized files raise PayloadTooLargeError and do not leave orphaned files."""
    # 200 bytes with limit of 100 bytes
    large_content = b"A" * 200
    upload = UploadFile(file=io.BytesIO(large_content), filename="large.txt")

    with pytest.raises(PayloadTooLargeError):
        save_upload_safely(upload, tmp_path, max_size_bytes=100)

    # Ensure no leftover files in tmp_path
    remaining_files = list(tmp_path.glob("*.dat"))
    assert len(remaining_files) == 0


def test_save_upload_safely_valid_txt(tmp_path: Path):
    """Verify valid upload streams correctly to server-controlled filename."""
    content = b"This is a valid plaintext document content."
    upload = UploadFile(file=io.BytesIO(content), filename="my_notes.txt")

    sanitized_name, saved_path, size, mime = save_upload_safely(upload, tmp_path, max_size_bytes=1024)
    assert sanitized_name == "my_notes.txt"
    assert saved_path.exists()
    assert saved_path.name != "my_notes.txt"  # Server-controlled UUID filename
    assert saved_path.suffix == ".txt"
    assert size == len(content)
    assert mime == "text/plain"


def test_save_upload_safely_valid_markdown(tmp_path: Path):
    """Verify valid markdown (.md) upload streams correctly with text/markdown mime."""
    content = b"# Security Policy\n\nThis is a markdown document."
    upload = UploadFile(file=io.BytesIO(content), filename="README.md")

    sanitized_name, saved_path, size, mime = save_upload_safely(upload, tmp_path, max_size_bytes=1024)
    assert sanitized_name == "README.md"
    assert saved_path.exists()
    assert saved_path.suffix == ".md"
    assert size == len(content)
    assert mime == "text/markdown"
