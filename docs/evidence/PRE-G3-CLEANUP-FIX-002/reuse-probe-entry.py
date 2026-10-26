from pathlib import Path
import importlib.util,sys,os
sys.dont_write_bytecode=True
old=Path('/Users/chasen/.codex/worktrees/g2-master/ontology-platform')
current=Path('/Users/chasen/.codex/worktrees/pre-g3-hygiene/ontology-platform')
spec=importlib.util.spec_from_file_location('trusted_runtime',old/'scripts/acceptance/wave2-runtime.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.EVIDENCE=current/'artifacts/maintenance/PRE-G3-CLEANUP-FIX-002/reuse-probe'
m.EVIDENCE.mkdir(parents=True,exist_ok=True)
(m.EVIDENCE/'launcher.pid').write_text(str(os.getpid()))
sys.exit(m.run(old/'.tools/security/g2-ef979bd04cc0/runtime.json','full','g2','Release'))
