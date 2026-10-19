"""Secure upload validation service: file signature inspection, bounded streaming, and path safety."""

import io
import os
import posixpath
import re
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO, Optional, Set, Tuple

from fastapi import UploadFile

# Default maximum upload size: 10 MiB
DEFAULT_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10,485,760 bytes
CHUNK_READ_SIZE = 64 * 1024  # 64 KiB chunks for streaming reads

ALLOWED_EXTENSIONS: Set[str] = {".pdf", ".docx", ".txt", ".md"}
ALLOWED_MIME_TYPES: Set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}


class UploadValidationError(Exception):
    """Base exception for upload validation failures."""
    pass


class UnsupportedFormatError(UploadValidationError):
    """Raised when file extension or magic bytes do not match supported types."""
    pass


class PayloadTooLargeError(UploadValidationError):
    """Raised when uploaded file exceeds the configured maximum byte limit."""
    pass


class EmptyFileError(UploadValidationError):
    """Raised when an uploaded file contains 0 bytes."""
    pass


class MalformedFileError(UploadValidationError):
    """Raised when file structure is corrupt or spoofed."""
    pass


class PathTraversalError(UploadValidationError):
    """Raised when a storage path escapes the designated uploads root."""
    pass


def sanitize_filename(filename: str) -> str:
    """
    Sanitize user-provided filename to prevent directory traversal and header injection.
    Strips directory separators, relative path markers ('..'), and illegal characters.
    """
    if not filename or not filename.strip():
        return "unnamed_document.txt"

    # Normalize slashes and extract basename to strip any path traversal or absolute roots
    normalized = filename.strip().replace("\\", "/")
    cleaned = posixpath.basename(normalized)

    # Remove null bytes and control characters
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)

    # Replace path navigation markers
    cleaned = cleaned.replace("..", "").replace("/", "").replace("\\", "")

    # Restrict to safe alphanumeric, spaces, dashes, underscores, dots, parentheses, and brackets
    cleaned = re.sub(r"[^\w\s\.\-\(\)\[\]]", "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned or cleaned.startswith("."):
        cleaned = f"doc_{cleaned}" if cleaned else "unnamed_document.txt"

    # Limit length to 200 characters to fit database columns safely
    return cleaned[:200]


def inspect_file_signatures(header: bytes, ext: str, stream: BinaryIO) -> str:
    """
    Validate file integrity and signature against declared extension.
    Returns the verified normalized MIME type.
    """
    if len(header) == 0:
        raise EmptyFileError("Uploaded file is empty (0 bytes).")

    ext_lower = ext.lower()

    if ext_lower == ".pdf":
        # PDF files must start with %PDF- (standard offset 0 to 1024)
        if not (header.startswith(b"%PDF-") or b"%PDF-" in header[:1024]):
            raise UnsupportedFormatError(
                "Invalid PDF file signature. Content does not match PDF specification."
            )
        return "application/pdf"

    elif ext_lower == ".docx":
        # DOCX is an OpenXML ZIP archive starting with PK\x03\x04
        if not header.startswith(b"\x50\x4B\x03\x04"):
            raise UnsupportedFormatError(
                "Invalid DOCX file signature. File is not a valid OpenXML archive."
            )
        # Verify internal DOCX structure (word/document.xml)
        try:
            current_pos = stream.tell()
            stream.seek(0)
            with zipfile.ZipFile(stream) as zf:
                namelist = zf.namelist()
                if not any(name.startswith("word/") for name in namelist):
                    raise MalformedFileError(
                        "Malformed DOCX structure: missing 'word/' document payload."
                    )
            stream.seek(current_pos)
        except zipfile.BadZipFile as e:
            raise MalformedFileError("Corrupt DOCX archive.") from e
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    elif ext_lower in (".txt", ".md"):
        # Plaintext and Markdown files must not contain binary null bytes (\x00) and must decode as text
        if b"\x00" in header[:4096]:
            raise UnsupportedFormatError(
                "File contains binary null bytes; cannot be processed as plaintext."
            )
        # Verify safe text decodability
        decoded = False
        for encoding in ["utf-8", "utf-8-sig", "latin-1"]:
            try:
                header.decode(encoding)
                decoded = True
                break
            except UnicodeDecodeError:
                continue
        if not decoded:
            raise MalformedFileError("Plaintext file cannot be decoded with standard text encodings.")
        return "text/markdown" if ext_lower == ".md" else "text/plain"

    raise UnsupportedFormatError(
        f"Unsupported file format '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
    )


def save_upload_safely(
    upload_file: UploadFile,
    upload_dir: Path,
    max_size_bytes: int = DEFAULT_MAX_UPLOAD_SIZE,
) -> Tuple[str, Path, int, str]:
    """
    Validate, sanitize, stream, and save an uploaded file to disk.
    
    Returns:
        (sanitized_filename, final_storage_path, file_size_bytes, verified_mime_type)
    
    Raises:
        EmptyFileError, PayloadTooLargeError, UnsupportedFormatError, MalformedFileError
    """
    raw_filename = upload_file.filename or "unnamed_document.txt"
    sanitized_name = sanitize_filename(raw_filename)
    ext = Path(sanitized_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFormatError(
            f"File extension '{ext}' is not permitted. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    # Ensure upload directory exists and is strictly resolved
    upload_dir_resolved = upload_dir.resolve()
    upload_dir_resolved.mkdir(parents=True, exist_ok=True)

    # Server-controlled unique storage filename preserving extension (never uses client name on disk)
    storage_filename = f"{uuid.uuid4()}{ext}"
    final_path = (upload_dir_resolved / storage_filename).resolve()

    # Prevent path traversal
    try:
        final_path.relative_to(upload_dir_resolved)
    except ValueError as e:
        raise PathTraversalError("Target storage path escapes configured upload root.") from e

    # Stream file to disk in chunks to enforce bounded memory usage
    total_bytes = 0
    header_bytes = bytearray()
    header_captured = False

    try:
        with open(final_path, "wb") as out_file:
            while True:
                chunk = upload_file.file.read(CHUNK_READ_SIZE)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > max_size_bytes:
                    raise PayloadTooLargeError(
                        f"File size exceeds maximum allowed limit of {max_size_bytes // (1024 * 1024)} MiB."
                    )

                if not header_captured:
                    header_bytes.extend(chunk)
                    if len(header_bytes) >= 4096:
                        header_captured = True

                out_file.write(chunk)

        if total_bytes == 0:
            raise EmptyFileError("Uploaded file contains 0 bytes.")

        # Validate file signatures using the saved file
        with open(final_path, "rb") as check_file:
            verified_mime = inspect_file_signatures(bytes(header_bytes), ext, check_file)

        return sanitized_name, final_path, total_bytes, verified_mime

    except Exception:
        # Clean up partial/corrupt file on any failure
        if final_path.exists():
            try:
                final_path.unlink()
            except OSError:
                pass
        raise
