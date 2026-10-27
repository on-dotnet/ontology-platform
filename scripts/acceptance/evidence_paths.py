"""Choose bounded task evidence outputs without reading private runtime data."""
import os
from pathlib import Path


def evidence_directory(root, default):
    """Reject escape and symlink targets before any caller creates output."""
    root = Path(root).resolve()
    allowed = root / 'docs/evidence'
    selected = root / os.environ.get('PLATFORM_EVIDENCE_DIR', default)
    if not selected.is_relative_to(allowed) or '..' in selected.parts:
        raise ValueError('Evidence output must stay under repository docs/evidence')
    current = selected
    while current != root:
        if current.is_symlink():
            raise ValueError('Evidence output cannot traverse a symlink')
        current = current.parent
    if not selected.resolve().is_relative_to(allowed.resolve()):
        raise ValueError('Evidence output escaped repository boundary')
    return selected
