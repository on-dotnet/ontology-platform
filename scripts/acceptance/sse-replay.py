#!/usr/bin/env python3
"""Run the actual Kestrel/PG SSE replay, revocation and slow-client tests on fresh resources."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
raise SystemExit(subprocess.run([sys.executable, str(ROOT / "scripts/acceptance/mcp-agent.py"), "--label", "sse-replay", "--filter", "FullyQualifiedName~TransportTests"], cwd=ROOT).returncode)
