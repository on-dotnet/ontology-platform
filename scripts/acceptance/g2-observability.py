#!/usr/bin/env python3
"""Verify actual G2 product meters/traces/privacy through the running Alloy/LGTM pipeline."""
import argparse
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
from evidence_paths import evidence_directory
EVIDENCE = evidence_directory(ROOT, 'docs/evidence/G2-THIN-SLICE-001/master')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
VISIBILITY_BUDGET_SECONDS = 90
POLL_INTERVAL_SECONDS = 1


def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value,list):
        for child in value:
            yield from walk(child)


def fetch(origin,path,parameters=None,timeout=10):
    address = origin + path + ('?' + urllib.parse.urlencode(parameters) if parameters else '')
    with OPENER.open(address,timeout=timeout) as response:
        return json.load(response)


def read_chain_identifiers(directory):
    """任何真实请求或私有runtime读取前校验有界链路输入，缺失/坏Schema立即失败。"""
    path=Path(directory)/'full-chain-identifiers.json'
    if not path.is_file() or path.is_symlink() or path.stat().st_size>65536:
        raise ValueError('EVIDENCE_CHAIN_IDS_MISSING: 缺少受控链路标识输入或文件越界')
    value=json.loads(path.read_text(encoding='utf-8'))
    traces=value.get('traces') if isinstance(value,dict) else None
    if not isinstance(traces,list) or not 5<=len(traces)<=100 or not all(isinstance(item,str) and re.fullmatch('[a-f0-9]{32}',item) and item!='0'*32 for item in traces):
        raise ValueError('EVIDENCE_CHAIN_IDS_INVALID: 链路标识Schema无效')
    return value


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
    visibility_started = None
    visibility = {'budgetSeconds':VISIBILITY_BUDGET_SECONDS,'pollIntervalSeconds':POLL_INTERVAL_SECONDS,'pollCount':0,'elapsedSeconds':0,'requests':[]}
    report_path = EVIDENCE / 'g2-observability.json'
    def persist_report(status):
        # Atomic replacement keeps a failed PASS write from truncating the persisted FAIL.
        if visibility_started is not None:
            visibility['elapsedSeconds'] = round(time.monotonic()-visibility_started,3)
        report = {'status':status,'checks':checks,'visibility':visibility,'workerTraceDesign':'actual independent execution.run trace with persisted creation_trace_id tag; never a fabricated parent span','officialSearchApi':'https://grafana.com/docs/tempo/latest/api_docs/','scope':'actual product emissions, own local synthetic stack; no model calls or production data'}
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
    def privacy(value,record=True):
        text = json.dumps(value,ensure_ascii=False)
        safe = all(secret not in text for secret in forbidden)
        if record or not safe:
            check('actual_export_contains_no_prompt_source_or_private_runtime_values',safe)
    def visible(name,origin,address,parameters,present):
        # All backends share one deadline. Only absence and temporary transport failures retry.
        started = time.monotonic()
        request = {'check':name,'polls':0,'elapsedSeconds':0,'state':'pending'}
        visibility['requests'].append(request)
        try:
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    request['state'] = 'timeout'
                    raise TimeoutError('G2 telemetry visibility budget exhausted')
                request['polls'] += 1
                visibility['pollCount'] += 1
                try:
                    value = fetch(origin,address,parameters,timeout=min(10,remaining))
                except urllib.error.HTTPError as failure:
                    trace_pending = failure.code == 404 and address.startswith('/api/traces/')
                    if not trace_pending and failure.code not in {408,425,429,500,502,503,504}:
                        request['state'] = 'rejected_http'
                        raise
                    request['state'] = 'trace_not_visible' if trace_pending else 'temporary_http'
                except (urllib.error.URLError,TimeoutError,ConnectionError):
                    request['state'] = 'temporary_network'
                else:
                    if time.monotonic() >= deadline:
                        request['state'] = 'timeout'
                        raise TimeoutError('G2 telemetry visibility budget exhausted')
                    privacy(value,record=False)
                    ready = present(value)
                    if time.monotonic() >= deadline:
                        request['state'] = 'timeout'
                        raise TimeoutError('G2 telemetry visibility budget exhausted')
                    if ready:
                        request['state'] = 'visible'
                        return value
                    request['state'] = 'not_visible'
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    request['state'] = 'timeout'
                    raise TimeoutError('G2 telemetry visibility budget exhausted')
                time.sleep(min(POLL_INTERVAL_SECONDS,remaining))
        finally:
            request['elapsedSeconds'] = round(time.monotonic()-started,3)
    try:
        # Invalidate an earlier run before any I/O can fail; never leave a stale PASS.
        report_path.unlink(missing_ok=True)
        persist_report('FAIL')
        identities = read_chain_identifiers(EVIDENCE)
        runtime = json.loads(path.read_text())
        realm = json.loads(Path(runtime['realmFile']).read_text())
        forbidden = [runtime[key] for key in ['postgresPassword','keycloakPassword','grafanaPassword','certificatePassword','healthKey','rustfsAccessKey','rustfsSecretKey']]
        forbidden += [realm['clientSecret'],'G2_PROMPT_MUST_NOT_LEAK_','# 人工合成，两个厂区外部号相同']
        traces = identities['traces']
        check('only_real_valid_persisted_trace_ids',len(traces)>=5 and all(re.fullmatch('[a-f0-9]{32}',value) and value != '0'*32 for value in traces))
        visibility_started = time.monotonic()
        deadline = visibility_started+VISIBILITY_BUDGET_SECONDS
        has_spans = lambda value: bool([span for span in walk(value) if 'spanId' in span and 'name' in span])
        for trace in traces:
            value = visible('actual_tempo_trace_'+trace,'http://localhost:13200','/api/traces/'+trace,None,has_spans)
            check('actual_tempo_trace_'+trace,bool([span for span in walk(value) if 'spanId' in span and 'name' in span]))
            privacy(value)
            raw['trace-'+trace] = value
        creation_trace = traces[2]
        search = visible('worker_search','http://localhost:13200','/api/search',{'tags':'execution.creation_trace_id='+creation_trace,'limit':'20'},lambda value: bool(value['traces']))
        workers = search.get('traces',[])
        check('worker_real_separate_trace_associated_to_creation',bool(workers) and all(item['traceID'] != creation_trace for item in workers))
        worker = visible('worker_trace','http://localhost:13200','/api/traces/'+workers[0]['traceID'],None,has_spans)
        check('actual_maf_worker_and_gateway_spans',any(span.get('name')=='execution.run' for span in walk(worker)) and any(span.get('name')=='semantic.query' for span in walk(worker)))
        check('actual_worker_creation_link_tag',any(attr.get('key')=='execution.creation_trace_id' and attr.get('value',{}).get('stringValue')==creation_trace for attr in walk(worker)))
        privacy(worker)
        raw['worker-search'] = search
        raw['worker-trace'] = worker
        query = '{service_name="ontology-platform-api",service_version="G2-THIN-SLICE-001"}'
        logs = visible('g2_loki_entries','http://localhost:13100','/loki/api/v1/query_range',{'query':query,'limit':'5000','since':'30m'},lambda value: bool(value['data']['result']))
        check('actual_g2_loki_entries',bool(logs['data']['result']))
        privacy(logs)
        raw['g2-loki'] = logs
        series = visible('g2_loki_series','http://localhost:13100','/loki/api/v1/series',{'match[]':query,'start':str(time.time_ns()-1800_000_000_000)},lambda value: bool(value['data']))
        check('actual_loki_only_three_index_dimensions',bool(series.get('data')) and all(set(item)=={'service_name','service_version','deployment_environment_name'} for item in series['data']))
        raw['g2-loki-series'] = series
        all_series = []
        forbidden_dimensions = {'assetId','asset_id','runId','run_id','traceId','trace_id','releaseId','release_id','subject_id','site_id','prompt','sourceId','source_id','organization_id'}
        actual_ids = [*identities['ids'].values(),*traces]
        finite = {'capability':{'describe_ontology','resolve_entity','traverse_relationships'},'status':{'Found','Empty','Partial','Unavailable','Unauthorized','Ambiguous','allowed','failure'},'operation':{'AnalyzeAsync','ValidateAsync','ApplyEditAsync','DeployAsync','VerifyAsync','ReadPublishedAsync','ReadVerifiedPublishedAsync','publish','rollback','outbox'},'outcome':{'completed','failed'},'phase':{'lease','verify','consume','commit','prepare_or_commit'}}
        dimensions_valid = lambda items: all(not(set(item)&forbidden_dimensions) and all(value not in actual_ids and 'G2_PROMPT' not in value for value in item.values()) for item in items)
        values_valid = lambda items: all(item[key] in values for item in items for key,values in finite.items() if key in item)
        def metric_visible(value):
            if value.get('status') != 'success':
                check('actual_product_meter_'+metric,False)
            items = value['data']
            if not dimensions_valid(items):
                check('product_metrics_no_identity_prompt_or_source_dimensions',False)
            if not values_valid(items):
                check('product_metric_values_respect_actual_finite_contract',False)
            return bool(items)
        for metric in ['ontology_semantic_duration_milliseconds_count','publishing_operations_total','semantic_query_count_total','agents_run_count_total']:
            value = visible('product_meter_'+metric,'http://localhost:19095','/api/v1/series',{'match[]':metric},metric_visible)
            check('actual_product_meter_'+metric,value.get('status')=='success' and bool(value.get('data')))
            all_series += value['data']
            raw['metric-'+metric] = value
        check('product_metrics_no_identity_prompt_or_source_dimensions',dimensions_valid(all_series))
        check('product_metric_values_respect_actual_finite_contract',values_valid(all_series))
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
