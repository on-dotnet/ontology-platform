"""Task-private SELECT-only transport A/B driver; never a formal gate."""
import argparse,asyncio,json,sys
from pathlib import Path
W=Path("/Users/chasen/.codex/worktrees/g4-m1-main-integration-001/ontology-platform")
sys.path.insert(0,str(W/'experiments/g4-m1-main-integration'))
import runtime as rt
parser=argparse.ArgumentParser()
parser.add_argument('runtime_source')
parser.add_argument('--ingress',choices=['modules-agent'],required=True)
parser.add_argument('--run-id',required=True)
parser.add_argument('--expected-head',required=True)
parser.add_argument('--resource-manifest',required=True)
parser.add_argument('--evidence-dir',required=True)
parser.add_argument('--variant',choices=['original','nodelay'],required=True)
args=parser.parse_args()
rt.require(Path(args.runtime_source)==rt.HERE/'runtime.py','EXACT_RUNTIME_SOURCE')
m=rt.load_manifest(args.resource_manifest,args.run_id,args.expected_head)
rt.require(args.run_id=='b-continue-20261104-20' and args.expected_head=='7bb08672c354fb97ed39ad4ad7492d2cbe297aad','EXACT_DIAGNOSTIC_INPUT')
directory=rt.ARTIFACTS/args.run_id/('diagnostics/transport-'+args.variant)
rt.require(Path(args.evidence_dir)==directory,'EXACT_DIAGNOSTIC_OUTPUT')
rt.boundary(directory,rt.ARTIFACTS/args.run_id,exists=True)
original=rt.RELAY_PERL
rt.require(rt.digest(original.encode())=="6c696d8609020e5db1ef1804b5a168b5a1f738a7ba1a7bea41e70756c829bffc",'BASE_RELAY_DRIFT')
needle='socket(my $tcp,PF_INET,SOCK_STREAM,0) or die "SOCKET\\n";'
rt.require(original.count(needle)==1,'EXACT_RELAY_INSERTION')
setting='setsockopt($tcp,Socket::IPPROTO_TCP(),Socket::TCP_NODELAY(),pack("i",1)) or die "TCP_NODELAY\\n";' if args.variant=='nodelay' else ''
expected=1 if args.variant=='nodelay' else 0
addition='\nif($port==5432){\n'+setting+'\nmy $nodelay=getsockopt($tcp,Socket::IPPROTO_TCP(),Socket::TCP_NODELAY());\ndie "TCP_NODELAY_READBACK\\n" unless defined($nodelay) && unpack("i",$nodelay)=='+str(expected)+';\n}'
rt.RELAY_PERL=original.replace(needle,needle+addition)

rt.write_json(directory/'variant-inputs.json',{'taskId':rt.TASK,'runId':m['runId'],'testedCommit':m['_head'],'scope':'DIAGNOSTIC_ONLY_NOT_FORMAL_GATE','variant':args.variant,'getsockoptExpected':expected,'helperSha256':rt.digest(Path(__file__).read_bytes()),'runtimeSourceSha256':rt.digest((rt.HERE/'runtime.py').read_bytes()),'originalRelaySha256':rt.digest(original.encode()),'effectiveRelaySha256':rt.digest(rt.RELAY_PERL.encode()),'effectiveRelay':rt.RELAY_PERL,'mutation':'Variant changes only platform PG port5432 TCP_NODELAY=1, requires actual getsockopt==1 before connect; all other allowed routes, bytes, queries and budgets unchanged'})
asyncio.run(rt.ingress_daemon(m,args.ingress,evidence_directory=directory))
