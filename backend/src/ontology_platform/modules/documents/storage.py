"""Content-addressed storage for original documents."""

import hashlib
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol


class DocumentStorage(Protocol):
    def save(self, data: bytes) -> tuple[str, str]: ...

    def open(self, storage_key: str) -> bytes: ...


class LocalDocumentStorage:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def save(self, data: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        key = f"{digest[:2]}/{digest}"
        path = self.root / key
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=path.parent, delete_on_close=False) as staged:
                staged.write(data)
                staged.close()
                Path(staged.name).replace(path)
        return key, digest

    def open(self, storage_key: str) -> bytes:
        if not re.fullmatch(r"([0-9a-f]{2})/\1[0-9a-f]{62}", storage_key):
            raise ValueError("Invalid document storage key")
        return (self.root / storage_key).read_bytes()
