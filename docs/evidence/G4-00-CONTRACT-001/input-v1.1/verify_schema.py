#!/usr/bin/env python3
"""G4-00 v1.1 strict Draft2020-12 verification; runs only if jsonschema already installed.

No installation, subprocess, external network, credentials, or database.
"""
from pathlib import Path
import copy, json, re, sys
ROOT=Path(__file__).resolve().parent
try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    print('NOT_RUN: jsonschema is unavailable; no auto-install. Schema verification remains blocked.',file=sys.stderr)
    sys.exit(3)

def main():
    schema=json.loads((ROOT/'contracts/g4-proposed-wire-contract.schema.json').read_text('utf-8'))
    Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema,format_checker=FormatChecker())
    positive=json.loads((ROOT/'samples/g4-design-positive-synthetic.json').read_text('utf-8'))
    negatives=json.loads((ROOT/'samples/g4-wire-contract-v11-negative-mutations.json').read_text('utf-8'))
    for i,sample in enumerate(positive):
        errs=list(validator.iter_errors(sample))
        assert not errs,(f'positive sample {i}: {sample["schemaKind"]}',[(x.json_path,x.message) for x in errs[:5]])
    for bad in negatives:
        assert not validator.is_valid(bad['payload']),f'negative {bad["caseId"]} unexpectedly valid'
    # ensure REST JSON examples are identical in shape to strict wrapper.payload
    api=(ROOT/'docs/05-DATA-API-CONTRACT.md').read_text('utf-8')
    def fenced_after(marker):
        section=api[api.index(marker):]
        match=re.search(r'```json\s*\n(.*?)\n```',section,re.S)
        assert match,marker
        return json.loads(match.group(1))
    create=fenced_after('### 5.1 连接创建唯一请求')
    release=fenced_after('### 5.2 MappingRelease')
    assert validator.is_valid({'schemaKind':'ConnectionCreateRequest','payload':create}),'Markdown connection JSON not valid'
    assert validator.is_valid({'schemaKind':'MappingReleaseView','payload':release}),'Markdown mapping release JSON not valid'
    # Cross-ref tests address a semantic limitation JSON Schema itself cannot prove.
    def syntactic_semantic_check(sample):
        kind=sample['schemaKind']; p=sample['payload']
        if kind=='G4QueryResultV1':
            evid={x['evidenceId']:x for x in p['evidence']}
            # Design fixture carries only SITE_A / ORG_SYN. In runtime, the actor's
            # authorized scope comes from validated server identity, not this file.
            for ref in p['evidence']:
                if not set(ref['scope']['siteIds']) <= {'SITE_A'} or ref['scope']['organizationId']!='ORG_SYN':return False
            for cand in p['candidates']:
                if not set(cand['evidenceIds']) <= evid.keys():return False
                if cand['siteId'] not in {'SITE_A'} or cand['organizationId']!='ORG_SYN':return False
                if any(cand['siteId'] not in evid[i]['scope']['siteIds'] for i in cand['evidenceIds']):return False
            for item in p['data']:
                if not set(item['evidenceIds']) <= evid.keys():return False
            if p['status']=='AMBIGUOUS' and len(set(c['entityIri'] for c in p['candidates']))<2:return False
        if kind=='MappingProposalView' and p['decision'] is not None:
            if p['decision']['decidedBy']==p['submittedBy']:return False
        return True
    for sample in positive:
        assert syntactic_semantic_check(sample),f'positive synthetic semantic failure {sample["schemaKind"]}'
    semantic_negative=json.loads((ROOT/'samples/g4-wire-contract-v11-semantic-negative-cases.json').read_text('utf-8'))
    for bad in semantic_negative:
        assert validator.is_valid(bad['payload']),f'semantic-only negative {bad["caseId"]} should be schema-valid'
        assert not syntactic_semantic_check(bad['payload']),f'semantic-only negative {bad["caseId"]} unexpectedly accepted'
    print(json.dumps({'status':'DRAFT202012_SCHEMA_AND_CONTRACT_EXAMPLES_PASS','schemaKinds':len(schema['oneOf']),'positive':len(positive),'expectedSchemaRejected':len(negatives),'expectedSemanticRejected':len(semantic_negative),'inlineMarkdown':2,'evidenceCrossReferences':'PASS','schemaRuntime':'LOCAL_ONLY','g4ServiceRuntime':'NOT_RUN'},ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except AssertionError as e:
        print('VALIDATION_FAILED:',e,file=sys.stderr);sys.exit(1)
