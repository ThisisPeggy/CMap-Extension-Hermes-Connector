"""Bounded attachment staging for authenticated Browser WebSockets."""

import base64
import binascii
import io
import os
import re
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

from gateway.platforms.base import cache_document_from_bytes, cache_image_from_bytes


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_SESSION_BYTES = 50 * 1024 * 1024
MAX_SESSION_ATTACHMENTS = 12
MAX_GLOBAL_PENDING_BYTES = 100 * 1024 * 1024
MAX_GLOBAL_PENDING_ATTACHMENTS = 24
MAX_ARCHIVE_MEMBERS = 10_000

TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".json", ".csv", ".ts", ".tsx", ".js",
    ".jsx", ".mjs", ".css", ".html", ".xml", ".yaml", ".yml", ".toml",
    ".py", ".rs", ".go", ".java", ".c", ".cpp", ".h", ".hpp", ".sql",
    ".log",
}
DOCUMENT_MIME_TYPES = {
    **{suffix: "text/plain" for suffix in TEXT_SUFFIXES},
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
DATA_URL_RE = re.compile(r"data:([^;,]+);base64,([A-Za-z0-9+/]*={0,2})", re.IGNORECASE)


@dataclass(frozen=True)
class StagedAttachment:
    path: str
    mime_type: str
    size: int


class AttachmentStore:
    """Own staged media until one prompt consumes it or its socket closes."""

    def __init__(self, *, cache_image=cache_image_from_bytes, cache_document=cache_document_from_bytes):
        self._cache_image = cache_image
        self._cache_document = cache_document
        self._pending = {}
        self._lock = threading.Lock()

    def stage_image(self, owner, params):
        session_id = _session_id(params)
        data_url = params.get("data_url") or params.get("content_base64") or params.get("data")
        payload, declared_mime = _decode_data_url(data_url, expected_prefix="image/")
        suffix, mime_type = _sniff_image(payload)
        if declared_mime != mime_type:
            raise ValueError("image MIME type does not match its bytes")
        self._check_capacity(owner, session_id, len(payload))
        path = self._cache_image(payload, ext=suffix)
        attachment = StagedAttachment(path=path, mime_type=mime_type, size=len(payload))
        count = self._append_or_remove(owner, session_id, attachment)
        return {"attached": True, "count": count, "bytes": len(payload)}

    def stage_file(self, owner, params):
        session_id = _session_id(params)
        payload, declared_mime = _decode_data_url(params.get("data_url"))
        filename = Path(str(params.get("name") or params.get("path") or "")).name
        if not filename or len(filename) > 180:
            raise ValueError("a filename of at most 180 characters is required")
        suffix = Path(filename).suffix.lower()
        mime_type = DOCUMENT_MIME_TYPES.get(suffix)
        if not mime_type:
            raise ValueError("unsupported file type")
        if declared_mime not in {mime_type, "application/octet-stream", "text/plain"}:
            raise ValueError("file MIME type does not match its extension")
        _validate_document(payload, suffix)
        self._check_capacity(owner, session_id, len(payload))
        path = self._cache_document(payload, filename)
        attachment = StagedAttachment(path=path, mime_type=mime_type, size=len(payload))
        count = self._append_or_remove(owner, session_id, attachment)
        return {"attached": True, "name": filename, "count": count, "bytes": len(payload)}

    def take(self, owner, session_id):
        key = (owner, session_id)
        with self._lock:
            return self._pending.pop(key, [])

    def discard_owner(self, owner):
        with self._lock:
            keys = [key for key in self._pending if key[0] is owner]
            discarded = [attachment for key in keys for attachment in self._pending.pop(key)]
        _remove_files(discarded)

    def clear(self):
        with self._lock:
            discarded = [attachment for rows in self._pending.values() for attachment in rows]
            self._pending.clear()
        _remove_files(discarded)

    def _check_capacity(self, owner, session_id, size):
        key = (owner, session_id)
        with self._lock:
            self._raise_if_full(key, size)

    def _append_or_remove(self, owner, session_id, attachment):
        key = (owner, session_id)
        try:
            with self._lock:
                self._raise_if_full(key, attachment.size)
                pending = self._pending.setdefault(key, [])
                pending.append(attachment)
                return len(pending)
        except Exception:
            _remove_files([attachment])
            raise

    def _raise_if_full(self, key, incoming_size):
        pending = self._pending.get(key, [])
        if len(pending) >= MAX_SESSION_ATTACHMENTS:
            raise ValueError("attachment-count-limit")
        if sum(item.size for item in pending) + incoming_size > MAX_SESSION_BYTES:
            raise ValueError("attachment-total-size-limit")
        all_pending = [item for rows in self._pending.values() for item in rows]
        if len(all_pending) >= MAX_GLOBAL_PENDING_ATTACHMENTS:
            raise ValueError("connector-attachment-count-limit")
        if sum(item.size for item in all_pending) + incoming_size > MAX_GLOBAL_PENDING_BYTES:
            raise ValueError("connector-attachment-size-limit")


def _session_id(params):
    session_id = str(params.get("session_id") or "").strip()
    if not session_id or len(session_id) > 200:
        raise ValueError("session_id is required and must not exceed 200 characters")
    return session_id


def _decode_data_url(value, *, expected_prefix=""):
    match = DATA_URL_RE.fullmatch(str(value or "").strip())
    if not match:
        raise ValueError("attachment must be a base64 data URL")
    mime_type = match.group(1).strip().lower()
    if expected_prefix and not mime_type.startswith(expected_prefix):
        raise ValueError(f"attachment must use a {expected_prefix} MIME type")
    encoded = match.group(2)
    if len(encoded) > ((MAX_ATTACHMENT_BYTES + 2) // 3) * 4:
        raise ValueError("attachment-size-limit")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid-attachment-payload") from exc
    if not payload:
        raise ValueError("attachment is empty")
    if len(payload) > MAX_ATTACHMENT_BYTES:
        raise ValueError("attachment-size-limit")
    return payload, mime_type


def _sniff_image(payload):
    if payload[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png", "image/png"
    if payload[:3] == b"\xff\xd8\xff":
        return ".jpg", "image/jpeg"
    if payload[:6] in {b"GIF87a", b"GIF89a"}:
        return ".gif", "image/gif"
    if payload[:2] == b"BM":
        return ".bmp", "image/bmp"
    if payload[:4] == b"RIFF" and len(payload) >= 12 and payload[8:12] == b"WEBP":
        return ".webp", "image/webp"
    raise ValueError("unsupported or invalid image payload")


def _validate_document(payload, suffix):
    if suffix == ".pdf" and not payload.startswith(b"%PDF-"):
        raise ValueError("invalid PDF payload")
    if suffix in {".docx", ".xlsx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = archive.namelist()
        except (OSError, zipfile.BadZipFile) as exc:
            raise ValueError(f"invalid {suffix[1:].upper()} payload") from exc
        required_prefix = "word/" if suffix == ".docx" else "xl/"
        if len(names) > MAX_ARCHIVE_MEMBERS or "[Content_Types].xml" not in names or not any(
            name.startswith(required_prefix) for name in names
        ):
            raise ValueError(f"invalid {suffix[1:].upper()} payload")
    if suffix in TEXT_SUFFIXES and b"\x00" in payload:
        raise ValueError("text attachment contains binary data")


def _remove_files(attachments):
    for attachment in attachments:
        try:
            os.unlink(attachment.path)
        except OSError:
            pass
