#!/usr/bin/env python3
"""Verify actual G2 product meters/traces/privacy through the running Alloy/LGTM pipeline."""
import argparse
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/evidence/G2-THIN-SLICE-001/master'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value,list):
        for child in value:
            yield from walk(child)


def fetch(origin,path,parameters=None):
    address = origin + path + ('?' + urllib.parse.urlencode(parameters) if parameters else '')
    with OPENER.open(address,timeout=10) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-file',required=True)
    args = parser.parse_args()
    path = Path(args.runtime_file).resolve()
    if not path.is_relative_to((ROOT / '.tools/security').resolve()):
        parser.error('Only current checkout private runtime accepted')
    checks = []
    raw = {}
    completed = False
    report_path = EVIDENCE / 'g2-observability.json'
    def persist_report(status):
        # Atomic replacement keeps a failed PASS write from truncating the persisted FAIL.
        report = {'status':status,'checks':checks,'workerTraceDesign':'actual independent execution.run trace with persisted creation_trace_id tag; never a fabricated parent span','officialSearchApi':'https://grafana.com/docs/tempo/latest/api_docs/','scope':'actual product emissions, own local synthetic stack; no model calls or production data'}
        temporary = report_path.with_suffix('.json.tmp')
        try:
            temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            temporary.replace(report_path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    def check(name,value):
        checks.append({'check':name,'status':'PASS' if value else 'FAIL'})
        if not value:
            raise AssertionError('Actual G2 telemetry check failed')
    def privacy(value):
        text = json.dumps(value,ensure_ascii=False)
        check('actual_export_contains_no_prompt_source_or_private_runtime_values',all(secret not in text for secret in forbidden))
    try:
        # Invalidate an earlier run before any I/O can fail; never leave a stale PASS.
        report_path.unlink(missing_ok=True)
        persist_report('FAIL')
        runtime = json.loads(path.read_text())
        realm = json.loads(Path(runtime['realmFile']).read_text())
        identities = json.loads((EVIDENCE / 'full-chain-identifiers.json').read_text())
        forbidden = [runtime[key] for key in ['postgresPassword','keycloakPassword','grafanaPassword','certificatePassword','healthKey','rustfsAccessKey','rustfsSecretKey']]
        forbidden += [realm['clientSecret'],'G2_PROMPT_MUST_NOT_LEAK_','# 人工合成，两个厂区外部号相同']
        traces = identities['traces']
        check('only_real_valid_persisted_trace_ids',len(traces)>=5 and all(re.fullmatch('[a-f0-9]{32}',value) and value != '0'*32 for value in traces))
        for trace in traces:
            value = fetch('http://localhost:13200','/api/traces/'+trace)
            check('actual_tempo_trace_'+trace,bool([span for span in walk(value) if 'spanId' in span and 'name' in span]))
            privacy(value)
            raw['trace-'+trace] = value
        creation_trace = traces[2]
        search = fetch('http://localhost:13200','/api/search',{'tags':'execution.creation_trace_id='+creation_trace,'limit':'20'})
        workers = search.get('traces',[])
        check('worker_real_separate_trace_associated_to_creation',bool(workers) and all(item['traceID'] != creation_trace for item in workers))
        worker = fetch('http://localhost:13200','/api/traces/'+workers[0]['traceID'])
        check('actual_maf_worker_and_gateway_spans',any(span.get('name')=='execution.run' for span in walk(worker)) and any(span.get('name')=='semantic.query' for span in walk(worker)))
        check('actual_worker_creation_link_tag',any(attr.get('key')=='execution.creation_trace_id' and attr.get('value',{}).get('stringValue')==creation_trace for attr in walk(worker)))
        privacy(worker)
        raw['worker-search'] = search
        raw['worker-trace'] = worker
        query = '{service_name="ontology-platform-api",service_version="G2-THIN-SLICE-001"}'
        logs = fetch('http://localhost:13100','/loki/api/v1/query_range',{'query':query,'limit':'5000','since':'30m'})
        check('actual_g2_loki_entries',bool(logs['data']['result']))
        privacy(logs)
        raw['g2-loki'] = logs
        series = fetch('http://localhost:13100','/loki/api/v1/series',{'match[]':query,'start':str(time.time_ns()-1800_000_000_000)})
        check('actual_loki_only_three_index_dimensions',bool(series.get('data')) and all(set(item)=={'service_name','service_version','deployment_environment_name'} for item in series['data']))
        raw['g2-loki-series'] = series
        all_series = []
        for metric in ['ontology_semantic_duration_milliseconds_count','publishing_operations_total','semantic_query_count_total','agents_run_count_total']:
            value = fetch('http://localhost:19095','/api/v1/series',{'match[]':metric})
            check('actual_product_meter_'+metric,value.get('status')=='success' and bool(value.get('data')))
            all_series += value['data']
            raw['metric-'+metric] = value
        forbidden_dimensions = {'assetId','asset_id','runId','run_id','traceId','trace_id','releaseId','release_id','subject_id','site_id','prompt','sourceId','source_id','organization_id'}
        actual_ids = [*identities['ids'].values(),*traces]
        check('product_metrics_no_identity_prompt_or_source_dimensions',all(not(set(item)&forbidden_dimensions) and all(value not in actual_ids and 'G2_PROMPT' not in value for value in item.values()) for item in all_series))
        finite = {'capability':{'describe_ontology','resolve_entity','traverse_relationships'},'status':{'Found','Empty','Partial','Unavailable','Unauthorized','Ambiguous','allowed','failure'},'operation':{'AnalyzeAsync','ValidateAsync','ApplyEditAsync','DeployAsync','VerifyAsync','ReadPublishedAsync','ReadVerifiedPublishedAsync','publish','rollback','outbox'},'outcome':{'completed','failed'},'phase':{'lease','verify','consume','commit','prepare_or_commit'}}
        check('product_metric_values_respect_actual_finite_contract',all(item[key] in values for item in all_series for key,values in finite.items() if key in item))
        privacy(all_series)
        for name,value in raw.items():
            (EVIDENCE / (name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        persist_report('PASS')
        completed = True
        return 0
    finally:
        if not completed:
            persist_report('FAIL')
        print(json.dumps({'status':'PASS' if completed else 'FAIL','checks':len(checks)}))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as failure:
        print(json.dumps({'status':'FAIL','category':type(failure).__name__,'details':'SUPPRESSED'}))
        raise SystemExit(1)
