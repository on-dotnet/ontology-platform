"""Run real PG pause regression; each test owns a new approved container."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[5]
command = ['dotnet', 'test', '--project', 'backend/tests/OntologyPlatform.SecurityTests', '--no-restore', '--filter', 'FullyQualifiedName~G2ReadinessPostgresTests', '--output', 'Detailed']
result = subprocess.run(command, cwd=root)
print('exitCode=' + str(result.returncode))
sys.exit(result.returncode)
