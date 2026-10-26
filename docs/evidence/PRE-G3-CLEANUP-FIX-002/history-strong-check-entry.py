from pathlib import Path
import json,subprocess,datetime
root=Path.cwd();e=root/'docs/evidence/PRE-G3-CLEANUP-FIX-002';plan=json.loads((root/'artifacts/maintenance/PRE-G3-CLEANUP-FIX-002/history-plan.json').read_text());backend=plan['historyBackend'];rows=[]
fmt='{"Ref":{{printf "%q" .Ref}}}'
for op in plan['operations']:
 target=op['target'];args=['docker','buildx','history','inspect','--builder','desktop-linux','--format',fmt,target];r=subprocess.run(args,capture_output=True,text=True);expected='ERROR: no record found for ref "'+target+'"';ok=r.returncode==1 and not r.stdout and r.stderr.strip()==expected
 rows.append(dict(target=target,command=args,exitCode=r.returncode,stdoutEmpty=not r.stdout,stderrExactExpectedNoRecord=ok,diagnostic='EXACT_ID_NO_RECORD' if ok else 'UNEXPECTED_RESPONSE_RAW_SUPPRESSED'));assert ok,'Strong DB absence failed for '+target
checks=[(['docker','context','show'],backend['context']),(['docker','info','--format','{{.ID}}'],backend['engineId']),(['docker','network','inspect','bridge','--format','{{.Id}}'],backend['bridgeId'])]
for args,want in checks:assert subprocess.check_output(args,text=True).strip()==want
out=dict(observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='PASS_EXACT18_DB_ABSENCE',backend=backend,rows=rows,scope='Only exact previously approved18 IDs, no raw record/log/env/BuildArgs. exit1 only counts with exact expected identifier diagnostic; tombstones and transport failures do not count.')
(e/'history-strong-after.json').write_text(json.dumps(out,indent=2)+'\n');print('18/18 exact DB-absence diagnoses; backend generation unchanged')
