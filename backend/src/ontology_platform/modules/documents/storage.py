"""Content-addressed storage for original documents, and files derived from them.

Derived files (such as the transcripts of a scan's parts) belong to one document and let a
retried job reuse paid-for model output instead of producing it again.
"""

import hashlib
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol
from uuid import UUID

_DERIVED_NAME = re.compile(r"[a-z0-9][a-z0-9.-]*")


class DocumentStorage(Protocol):
    def save(self, data: bytes) -> tuple[str, str]: ...

    def open(self, storage_key: str) -> bytes: ...

    def save_derived(self, document_id: UUID, name: str, data: bytes) -> None: ...

    def open_derived(self, document_id: UUID, name: str) -> bytes | None: ...


def _write_atomically(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete_on_close=False) as staged:
        staged.write(data)
        staged.close()
        Path(staged.name).replace(path)


class LocalDocumentStorage:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def save(self, data: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        key = f"{digest[:2]}/{digest}"
        path = self.root / key
        if not path.is_file():
            _write_atomically(path, data)
        return key, digest

    def open(self, storage_key: str) -> bytes:
        if not re.fullmatch(r"([0-9a-f]{2})/\1[0-9a-f]{62}", storage_key):
            raise ValueError("Invalid document storage key")
        return (self.root / storage_key).read_bytes()

    def _derived_path(self, document_id: UUID, name: str) -> Path:
        if not _DERIVED_NAME.fullmatch(name) or ".." in name:
            raise ValueError("Invalid derived file name")
        return self.root / "derived" / str(document_id) / name

    def save_derived(self, document_id: UUID, name: str, data: bytes) -> None:
        """Replaces the file; a reader sees the old or the new content, never a partial one."""
        _write_atomically(self._derived_path(document_id, name), data)

    def open_derived(self, document_id: UUID, name: str) -> bytes | None:
        path = self._derived_path(document_id, name)
        return path.read_bytes() if path.is_file() else None
