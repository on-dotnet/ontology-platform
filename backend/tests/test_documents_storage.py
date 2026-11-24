import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from ontology_platform.modules.documents.storage import LocalDocumentStorage


def test_save_and_open_content_addressed_file(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    digest = hashlib.sha256(b"data").hexdigest()
    key = f"{digest[:2]}/{digest}"
    assert storage.save(b"data") == (key, digest)
    assert storage.save(b"data") == (key, digest)
    assert storage.open(key) == b"data"
    assert list((tmp_path / digest[:2]).iterdir()) == [tmp_path / key]


def test_atomic_publication_cleans_up_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_replace(source: Path, target: Path) -> None:
        assert source.read_bytes() == b"original"
        assert source.parent == target.parent
        assert not target.exists()
        raise OSError("write failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    storage = LocalDocumentStorage(tmp_path)
    with pytest.raises(OSError, match="write failed"):
        storage.save(b"original")
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_open_rejects_parent_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="storage key"):
        LocalDocumentStorage(tmp_path).open("../private")


def test_derived_files_are_kept_per_document(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    owner = uuid4()
    assert storage.open_derived(owner, "transcript-1-5.json") is None

    storage.save_derived(owner, "transcript-1-5.json", b"[]")
    storage.save_derived(owner, "transcript-1-5.json", b'[{"number": 1}]')

    assert storage.open_derived(owner, "transcript-1-5.json") == b'[{"number": 1}]'
    assert storage.open_derived(uuid4(), "transcript-1-5.json") is None
    assert [p.name for p in (tmp_path / "derived" / str(owner)).iterdir()] == [
        "transcript-1-5.json"
    ]


@pytest.mark.parametrize("name", ["../escape.json", "a/b.json", "", "Transcript.JSON"])
def test_derived_names_stay_in_their_folder(tmp_path: Path, name: str) -> None:
    storage = LocalDocumentStorage(tmp_path)
    with pytest.raises(ValueError, match="derived file name"):
        storage.save_derived(uuid4(), name, b"x")
    with pytest.raises(ValueError, match="derived file name"):
        storage.open_derived(uuid4(), name)
