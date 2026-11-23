"""scripts/mirror-lock.sh, which redirects the image's copy of uv.lock to a PyPI mirror."""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mirror-lock.sh"
LOCK = (
    'source = { registry = "https://pypi.org/simple" }\n'
    'wheels = [{ url = "https://files.pythonhosted.org/packages/ab/cd/demo.whl" }]\n'
)


def run_script(lock: Path, files_mirror: str, index: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin", "PYPI_FILES_MIRROR": files_mirror, "PIP_INDEX_URL": index}
    return subprocess.run(
        ["/bin/sh", str(SCRIPT), str(lock)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def lock(tmp_path: Path) -> Path:
    path = tmp_path / "uv.lock"
    path.write_text(LOCK)
    return path


def test_rewrites_downloads_and_registry(lock: Path) -> None:
    result = run_script(lock, "https://mirror.example/pypi/", "https://mirror.example/simple/")

    assert result.returncode == 0, result.stderr
    content = lock.read_text()
    assert "https://mirror.example/pypi/packages/ab/cd/demo.whl" in content
    assert 'registry = "https://mirror.example/simple"' in content
    assert "files.pythonhosted.org" not in content


def test_does_nothing_without_a_mirror(lock: Path) -> None:
    result = run_script(lock, "", "https://mirror.example/simple/")

    assert result.returncode == 0
    assert lock.read_text() == LOCK


@pytest.mark.parametrize(
    ("files_mirror", "index"),
    [
        ("https://mirror.example/a&b/", "https://mirror.example/simple"),
        ("https://mirror.example/#/", "https://mirror.example/simple"),
        ("https://mirror.example/a\\b/", "https://mirror.example/simple"),
        ("https://mirror.example/a|b/", "https://mirror.example/simple"),
        ("https://mirror.example/pypi/", "https://mirror.example/simple?a&b"),
    ],
)
def test_rejects_characters_that_break_sed(lock: Path, files_mirror: str, index: str) -> None:
    result = run_script(lock, files_mirror, index)

    assert result.returncode != 0
    assert lock.read_text() == LOCK


def test_fails_when_upstream_urls_remain(lock: Path) -> None:
    lock.write_text('url = "http://files.pythonhosted.org/packages/demo.whl"\n')

    result = run_script(lock, "https://mirror.example/pypi/", "https://mirror.example/simple/")

    assert result.returncode != 0
    assert "files.pythonhosted.org" in result.stderr
