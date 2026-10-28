#!/usr/bin/env python3
"""Read-only arm64 transfer guards. Missing account confirmation always blocks.

No upload, download, token access, billing mutation or runner creation exists here.
"""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import sys
import time
import urllib.request
from urllib.parse import parse_qs, urlsplit

ROOT=Path(__file__).resolve().parents[2]
REPOSITORY='on-dotnet/ontology-platform'
PROOF_PATH=ROOT/'docs/evidence/G3-M3-001/master/arm64-transfer-budget-proof.json'
MIB=1024**2
CONSERVATIVE_LIMIT=450*MIB
TRANSFER_LIMIT=512*MIB
UPLOAD_RESERVE=8*MIB
ENV_KEYS=('GITHUB_ACTIONS','GITHUB_EVENT_NAME','GITHUB_REPOSITORY','GITHUB_SHA','GITHUB_RUN_ID',
          'GITHUB_RUN_ATTEMPT','GITHUB_REF','RUNNER_OS','RUNNER_ARCH','RUNNER_ENVIRONMENT','GITHUB_EVENT_PATH')


class TransferRefused(Exception):
    """A fixed refusal category contains no untrusted values."""
    def __init__(self,category):
        super().__init__(category)
        self.category=category


def require(condition,category):
    if not condition:raise TransferRefused(category)


def strict_json(raw):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise TransferRefused('JSON_SCHEMA_INVALID')
            value[key]=item
        return value
    try:return json.loads(raw,object_pairs_hook=pairs)
    except (ValueError,TypeError):raise TransferRefused('JSON_SCHEMA_INVALID') from None


def proof_headroom(proof,now):
    require(proof is not None,'ACCOUNT_BUDGET_UNKNOWN')
    fields={'schemaVersion','repository','owner','confirmedAtUtc','hardSpendLimitUSD','remainingIncludedBytes',
            'humanConfirmed','confirmationSource','scope'}
    require(isinstance(proof,dict) and set(proof)==fields,'BUDGET_PROOF_SCHEMA')
    require(type(proof['schemaVersion']) is int and proof['schemaVersion']==1 and proof['repository']==REPOSITORY and
            proof['owner']=='on-dotnet' and type(proof['hardSpendLimitUSD']) is int and proof['hardSpendLimitUSD']==0 and
            proof['humanConfirmed'] is True and proof['confirmationSource']=='human-current-session' and
            proof['scope']=='owner-actions-artifacts-and-packages' and type(proof['remainingIncludedBytes']) is int and
            0<=proof['remainingIncludedBytes']<=500*MIB,'BUDGET_PROOF_INVALID')
    try:observed=dt.datetime.fromisoformat(proof['confirmedAtUtc'].replace('Z','+00:00'))
    except (ValueError,TypeError,AttributeError):raise TransferRefused('BUDGET_PROOF_TIME') from None
    require(observed.utcoffset()==dt.timedelta(0) and 0<=(now-observed).total_seconds()<=3600,'BUDGET_PROOF_TIME')
    return proof['remainingIncludedBytes']


def public_repository(repo):
    require(isinstance(repo,dict) and repo.get('full_name')==REPOSITORY and repo.get('private') is False and
            repo.get('visibility')=='public' and type(repo.get('id')) is int and repo['id']>0,'PUBLIC_REPOSITORY_UNVERIFIED')
    return repo['id']


def context(env,event,system=None,machine=None):
    require(env.get('GITHUB_ACTIONS')=='true' and env.get('GITHUB_EVENT_NAME')=='workflow_dispatch' and
            env.get('GITHUB_REPOSITORY')==REPOSITORY and env.get('GITHUB_REF')=='refs/heads/main','DISPATCH_CONTEXT_INVALID')
    require(env.get('RUNNER_ENVIRONMENT')=='github-hosted' and env.get('RUNNER_OS')=='Linux' and env.get('RUNNER_ARCH')=='ARM64' and
            (system or platform.system())=='Linux' and (machine or platform.machine()) in ('arm64','aarch64'),'NATIVE_ARM64_REQUIRED')
    require(isinstance(event,dict) and set(event)<={'ref','repository','sender','organization','enterprise','inputs','workflow'} and
            event.get('ref') in ('main','refs/heads/main') and event.get('inputs',{}) in ({},None),'EVENT_SCHEMA_INVALID')
    repository_id=public_repository(event.get('repository'))
    require(bool(re.fullmatch(r'[0-9a-f]{40}',env.get('GITHUB_SHA',''))) and
            bool(re.fullmatch(r'[1-9][0-9]{0,19}',env.get('GITHUB_RUN_ID',''))) and
            bool(re.fullmatch(r'[1-9][0-9]{0,4}',env.get('GITHUB_RUN_ATTEMPT',''))),'RUN_IDENTITY_INVALID')
    return dict(repositoryId=repository_id,head=env['GITHUB_SHA'],runId=env['GITHUB_RUN_ID'],attempt=int(env['GITHUB_RUN_ATTEMPT']))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise TransferRefused('PUBLIC_API_REDIRECT')


class PublicApi:
    """Fixed-origin unauthenticated GETs with size, request and total-time bounds."""
    def __init__(self):
        self.deadline=time.monotonic()+25
        self.requests=0
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def __call__(self,path):
        require(bool(re.fullmatch(r'/repos/on-dotnet/ontology-platform(?:/actions/runs/[1-9][0-9]{0,19}|/actions/artifacts\?per_page=100&page=[1-3])?',path)),'PUBLIC_API_PATH')
        self.requests+=1
        require(self.requests<=5 and time.monotonic()<self.deadline,'PUBLIC_API_BUDGET')
        request=urllib.request.Request('https://api.github.com'+path,headers={
            'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'ontology-platform-fuseki-transfer-guard'},method='GET')
        try:
            with self.opener.open(request,timeout=min(5,self.deadline-time.monotonic())) as response:
                require(response.status==200 and response.geturl()=='https://api.github.com'+path,'PUBLIC_API_RESPONSE')
                raw=response.read(2*1024**2+1)
                require(len(raw)<=2*1024**2,'PUBLIC_API_SIZE')
                return strict_json(raw),dict(response.headers)
        except TransferRefused:raise
        except Exception:raise TransferRefused('PUBLIC_API_UNAVAILABLE') from None


def inventory(fetch):
    try:
        repo,_=fetch('/repos/'+REPOSITORY)
        repo_id=public_repository(repo)
        artifacts=[];total=None;seen=set()
        for page in range(1,4):
            path='/repos/'+REPOSITORY+'/actions/artifacts?per_page=100&page='+str(page)
            value,headers=fetch(path)
            require(isinstance(value,dict) and set(value)=={'total_count','artifacts'} and type(value['total_count']) is int and
                    0<=value['total_count']<=300 and isinstance(value['artifacts'],list),'ARTIFACT_INVENTORY_SCHEMA')
            if total is None:total=value['total_count']
            require(value['total_count']==total and len(value['artifacts'])==min(100,total-len(artifacts)),'ARTIFACT_PAGINATION_INCOMPLETE')
            for artifact in value['artifacts']:
                require(isinstance(artifact,dict) and type(artifact.get('id')) is int and artifact['id']>0 and artifact['id'] not in seen and
                        type(artifact.get('size_in_bytes')) is int and artifact['size_in_bytes']>=0 and
                        type(artifact.get('expired')) is bool and isinstance(artifact.get('name'),str),'ARTIFACT_METADATA_INVALID')
                seen.add(artifact['id']);artifacts.append(artifact)
            link=next((v for k,v in headers.items() if k.lower()=='link'),'')
            next_link=re.search(r'<([^>]+)>;\s*rel="next"',link)
            if len(artifacts)==total:
                require(next_link is None,'ARTIFACT_PAGINATION_INCOMPLETE');break
            require(next_link is not None and page<3,'ARTIFACT_PAGINATION_INCOMPLETE')
            target=urlsplit(next_link[1])
            require(target.scheme=='https' and target.netloc=='api.github.com' and target.path=='/repos/'+REPOSITORY+'/actions/artifacts' and
                    not target.fragment and parse_qs(target.query)=={'per_page':['100'],'page':[str(page+1)]},'ARTIFACT_PAGINATION_INCOMPLETE')
        require(len(artifacts)==total,'ARTIFACT_PAGINATION_INCOMPLETE')
        return dict(repositoryId=repo_id,publicOnly=True,artifactCount=total,currentBytes=sum(a['size_in_bytes'] for a in artifacts),
                    activeTransferCount=sum(not a['expired'] and a['name'].startswith('canonical-fuseki-arm64-') for a in artifacts))
    except TransferRefused:raise
    except Exception:raise TransferRefused('ARTIFACT_INVENTORY_UNKNOWN') from None


def confirm_run(fetch,ctx):
    try:
        run,_=fetch('/repos/'+REPOSITORY+'/actions/runs/'+ctx['runId'])
        require(isinstance(run,dict) and run.get('event')=='workflow_dispatch' and run.get('head_sha')==ctx['head'] and
                run.get('head_branch')=='main' and run.get('status')=='in_progress' and type(run.get('run_attempt')) is int and
                run['run_attempt']==ctx['attempt'] and public_repository(run.get('repository'))==ctx['repositoryId'] and
                public_repository(run.get('head_repository'))==ctx['repositoryId'],'LIVE_RUN_UNVERIFIED')
    except TransferRefused:raise
    except Exception:raise TransferRefused('LIVE_RUN_UNVERIFIED') from None


def budget(candidate_bytes,snapshot,proof,now):
    remaining=proof_headroom(proof,now)
    require(type(candidate_bytes) is int and 0<candidate_bytes<=TRANSFER_LIMIT,'TRANSFER_SIZE_INVALID')
    require(snapshot.get('publicOnly') is True and type(snapshot.get('currentBytes')) is int and snapshot['currentBytes']>=0 and
            snapshot.get('activeTransferCount')==0,'REPOSITORY_STORAGE_UNVERIFIED')
    require(candidate_bytes+UPLOAD_RESERVE<=remaining and snapshot['currentBytes']+candidate_bytes+UPLOAD_RESERVE<=CONSERVATIVE_LIMIT,'INCLUDED_STORAGE_INSUFFICIENT')
    return dict(status='BUDGET_CHECKED',uploadPerformed=False,conservativeLimitBytes=CONSERVATIVE_LIMIT,
                candidateBytes=candidate_bytes,currentRepositoryBytes=snapshot['currentBytes'],uploadReserveBytes=UPLOAD_RESERVE)


def load_canonical():
    spec=importlib.util.spec_from_file_location('transfer_canonical',ROOT/'scripts/maintenance/canonical_fuseki.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def validate_directory(directory,head):
    canonical=load_canonical()
    try:
        expected=canonical.identity(ROOT/'infra/development/fuseki','linux/arm64')
        receipt=canonical.validate_archive(directory,expected,stage='cache export')
        require(receipt['producerHead']==head and receipt['platform']=='linux/arm64','PRODUCER_IDENTITY_INVALID')
        size=sum(canonical.regular_file(Path(directory)/name,TRANSFER_LIMIT).stat().st_size for name in ('image.tar','receipt.json'))
        require(0<size<=TRANSFER_LIMIT,'TRANSFER_SIZE_INVALID')
        return size,receipt
    except TransferRefused:raise
    except Exception:raise TransferRefused('CANONICAL_ARCHIVE_INVALID') from None


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('preflight','validate'))
    parser.add_argument('--directory',type=Path,default=ROOT/'artifacts/fuseki-transfer')
    args=parser.parse_args(argv)
    try:
        # Whitelist reads exclude all token, credential and proxy environment variables.
        env={key:os.environ.get(key,'') for key in ENV_KEYS}
        require(PROOF_PATH.is_file(),'ACCOUNT_BUDGET_UNKNOWN')
        canonical=load_canonical()
        proof=strict_json(canonical.regular_file(PROOF_PATH,8192).read_bytes())
        now=dt.datetime.now(dt.timezone.utc);proof_headroom(proof,now)
        event=strict_json(canonical.regular_file(env['GITHUB_EVENT_PATH'],1024**2).read_bytes())
        ctx=context(env,event)
        fetch=PublicApi();snapshot=inventory(fetch)
        require(snapshot['repositoryId']==ctx['repositoryId'],'LIVE_REPOSITORY_MISMATCH')
        confirm_run(fetch,ctx)
        size=TRANSFER_LIMIT if args.mode=='preflight' else validate_directory(args.directory,ctx['head'])[0]
        # Preflight reserves only the confirmed feasible upper bound, never the 512MiB approval cap.
        if args.mode=='preflight':size=min(proof['remainingIncludedBytes'],CONSERVATIVE_LIMIT-snapshot['currentBytes'])-UPLOAD_RESERVE
        result=budget(size,snapshot,proof,now)
        result.update(mode=args.mode,repository=REPOSITORY,producerHead=ctx['head'],artifactCount=snapshot['artifactCount'])
        print(json.dumps(result,sort_keys=True));return 0
    except TransferRefused as failure:
        print(json.dumps(dict(status='BLOCKED',category=failure.category,uploadPerformed=False),sort_keys=True));return 2
    except Exception:
        print(json.dumps(dict(status='BLOCKED',category='GUARD_UNVERIFIED',uploadPerformed=False),sort_keys=True));return 2


if __name__=='__main__':sys.exit(main())
