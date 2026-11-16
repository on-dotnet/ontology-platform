#!/usr/bin/env python3
"""只读路径上下文及可信Git差异；搜索范围不是验收排除规则。"""
import argparse
import hashlib
import sys
import json
from pathlib import Path
import re
import subprocess

# 显式历史执行依赖同时登记gate指纹，不能按evidence目录排除。
HISTORICAL_EXECUTABLES = ('docs/evidence/G1-ENG-001/verify.tests.ps1',)
REQUIRED = ('global.json', 'Directory.Build.props', 'Directory.Packages.props', 'NuGet.Config',
            '.config/dotnet-tools.json', 'package.json', 'apps/web/package.json', 'pnpm-workspace.yaml',
            'turbo.json', '.node-version', 'AGENTS.md', 'PLANS.md', 'backend/AGENTS.md', 'apps/web/AGENTS.md',
            '.editorconfig', '.github/workflows/ci.yml', 'scripts/validate-structured-files.py',
            'scripts/verification-requirements.txt')


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def tree(root, ref):
    rows = {}
    for entry in git(root, 'ls-tree', '-r', '-z', ref).split(b'\0'):
        if not entry:
            continue
        info, path = entry.split(b'\t', 1)
        mode, kind, blob = info.decode().split()
        rows[path.decode()] = dict(mode=mode, kind=kind, blob=blob)
    return rows


def changed(root, base, head):
    """拒绝手填路径、脏树和非当前Head；--no-renames保留删除及重命名两侧。"""
    base = git(root, 'rev-parse', '--verify', base+'^{commit}').decode().strip()
    head = git(root, 'rev-parse', '--verify', head+'^{commit}').decode().strip()
    if git(root, 'status', '--porcelain').strip() or git(root, 'rev-parse', 'HEAD').decode().strip() != head:
        raise ValueError('INCREMENTAL_REQUIRES_CLEAN_CURRENT_HEAD')
    subprocess.run(['git', 'merge-base', '--is-ancestor', base, head], cwd=root, check=True, capture_output=True)
    return sorted(set(git(root, 'diff', '--name-only', '-z', '--no-renames', base, head, '--').decode().split('\0'))-{''})


def scope(root, base, head):
    """受改校验器/策略本身使全范围资格失效，其余按实际差异与固定依赖检查。"""
    import workflow
    paths = changed(root, base, head)
    classification = workflow.select_gates(paths)
    if classification['unknown']:
        raise ValueError('UNMAPPED_INPUTS: '+','.join(classification['unknown']))
    current = tree(root, head)
    policy = {'scripts/verify.ps1', 'scripts/validate-structured-files.py',
              'scripts/maintenance/workflow_context.py', 'scripts/maintenance/workflow.py', 'docs/development/verification-gates.json'}
    qualification = verified_base(root, base)
    # Markdown可改标题、链接目标或重命名：回全量保留原检查器的反向链接语义。
    full = bool(policy.intersection(paths)) or any(p.endswith('.md') for p in paths) or qualification is None
    selected = set(current) if full else set(paths) | set(REQUIRED)
    files = []
    for path in sorted(selected & current.keys()):
        if current[path]['mode'] not in ('100644', '100755') or (root/path).is_symlink():
            raise ValueError('INCREMENTAL_SPECIAL_PATH: '+path)
        files.append(path)
    # 原对象身份记录删除侧，未知缺失不能悄悄通过；固定required由原校验器检查。
    old = tree(root, base)
    return dict(schemaVersion=1, status='PASS', base=base, head=head, paths=files,
                changed=paths, deleted=[dict(path=p, **old[p]) for p in paths if p not in current and p in old],
                scope='ALL_TRACKED' if full else 'DIFF_AND_REQUIRED',
                executionMode='FRESH' if full else 'FRESH_AND_REUSED',
                reusedBase=None if full else qualification,
                reason='policy/markdown change or missing trustworthy Base qualification' if full else 'exact Base blobs and unchanged validator qualification',
                omissions='Unchanged files are outside incremental scope; no full-repository PASS is claimed.',
                productGates=sorted(set(classification['affected']) & {'environment','backend','web','contract','interaction'}))


def policy_identity(root):
    """资格绑定检查器、选择器和登记全部原字节；不是mtime资格。"""
    names=('scripts/verify.ps1','scripts/validate-structured-files.py','scripts/maintenance/workflow_context.py',
           'scripts/maintenance/workflow.py','docs/development/verification-gates.json')
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}


def qualification_path(root, commit):
    return root/'artifacts/workflow/policy-qualifications'/(commit+'.json')


def verified_base(root, base):
    """必须有既有执行器的真实完整命令原件；摘要/互相hash不能建立资格。"""
    from workflow_execution import sha,encoded
    path=qualification_path(root,base)
    try:
        row=json.loads(path.read_text())
        if row['commit']!=base or row['policy']!=policy_identity(root) or row['blobs']!=tree(root,base):return None
        if row['scope']!='ALL_TRACKED' or row.get('inputsUnchanged') is not True:return None
        original=root/row['command']['path']
        if original.is_symlink() or not original.resolve().is_relative_to((root/'artifacts/workflow').resolve()):return None
        if sha(original.read_bytes())!=row['command']['sha256']:return None
        receipt=json.loads(original.read_text())
        expected=['pwsh','-NoProfile','-File','scripts/verify.ps1','-BaseSha',row['base'],'-HeadSha',base]
        if receipt.get('commandSummary')!=dict(executable='pwsh',argumentCount=len(expected)-1,sha256=sha(encoded(expected))) or receipt.get('inputFingerprint')!=sha(encoded([row['blobs'],row['policy']])) or receipt.get('cwd')!=str(root) or receipt.get('exitCode')!=0 or receipt.get('classification')!='SUCCESS' or receipt.get('started') is not True:return None
        if receipt.get('stage')!='policy-complete-scan' or not receipt.get('commandId'):return None
        raw=b''
        for stream in ('stdout','stderr'):
            ref=receipt[stream];source=root/ref['path']
            if not source.resolve().is_relative_to(original.parent.resolve()) or source.is_symlink() or sha(source.read_bytes())!=ref['sha256']:return None
            raw+=source.read_bytes()
        if b'SCOPE: ALL_TRACKED;' not in raw or b'repository-static' not in raw or b'PASS:' not in raw:return None
        return dict(commit=base,receipt=str(path.relative_to(root)),sha256=sha(path.read_bytes()),
                    command=row['command'],blobs=len(row['blobs']))
    except (OSError,ValueError,KeyError,TypeError):return None


def check(root, base, head, task):
    """资格只能由此处实际调用完整原校验器产生；不提供自报PASS登记接口。"""
    import workflow
    from workflow_execution import run,sha,encoded
    selection=scope(root,base,head)
    before=tree(root,head);policy=policy_identity(root)
    command=['pwsh','-NoProfile','-File','scripts/verify.ps1','-BaseSha',base,'-HeadSha',head]
    result=run(command,root,task=task,stage='policy-complete-scan' if selection['scope']=='ALL_TRACKED' else 'policy-incremental-scan',
               environment=workflow.engineering_process_environment(task),input_key=sha(encoded([before,policy])),timeout=180)
    sys.stdout.buffer.write(result.stdout);sys.stderr.buffer.write(result.stderr)
    unchanged=not git(root,'status','--porcelain').strip() and before==tree(root,head) and policy==policy_identity(root)
    if result.returncode==0 and unchanged and selection['scope']=='ALL_TRACKED':
        original=root/'artifacts/workflow'/task/'commands'/result.receipt['runId']/result.receipt['commandId']/'receipt.json'
        if json.loads(original.read_text())!=result.receipt:raise ValueError('POLICY_COMMAND_ORIGINAL_DRIFT')
        path=qualification_path(root,head);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(dict(commit=head,base=base,policy=policy,blobs=before,scope='ALL_TRACKED',inputsUnchanged=True,
            command=dict(path=str(original.relative_to(root)),sha256=sha(original.read_bytes()))),sort_keys=True)+'\n')
    return result.returncode if unchanged else 65


def context(root, mode='code', task=None, query=None):
    """仅输出受管路径与Git来源；证据必须显式指定任务，正文不送入默认上下文。"""
    if mode not in ('code', 'evidence') or (mode == 'evidence' and not task):
        raise ValueError('CONTEXT_MODE_OR_TASK_REQUIRED')
    if task and not re.fullmatch('[A-Z0-9][A-Z0-9-]{1,79}', task):
        raise ValueError('CONTEXT_TASK_INVALID')
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    rows = tree(root, head)
    files = []
    for path, item in sorted(rows.items()):
        historical = path in HISTORICAL_EXECUTABLES
        if mode == 'evidence':
            include = path.startswith('docs/evidence/'+task+'/')
            category = 'EVIDENCE'
        else:
            code = not path.startswith('docs/') and not path.endswith('.md')
            spec = path in ('AGENTS.md','PLANS.md','apps/web/AGENTS.md','backend/AGENTS.md','docs/tasks/current-authorization.md',
                            'docs/tasks/'+str(task)+'.md','docs/planning/g4-implementation-plan.md') or path.startswith('docs/contracts/')
            include = code or spec or historical
            category = 'ENGINEERING_DEPENDENCY' if historical else ('CURRENT_SPEC' if spec else 'PRODUCT_ENGINEERING')
        if include and (not query or query.casefold() in path.casefold()):
            files.append(dict(path=path, category=category, source=head+':'+path, blob=item['blob']))
    missing = [p for p in HISTORICAL_EXECUTABLES if p not in rows] if mode == 'code' else []
    if missing or not files:
        raise ValueError('CONTEXT_REQUIRED_DEPENDENCY_OR_MATCH_MISSING')
    return dict(schemaVersion=1, status='PASS', mode=mode, taskId=task, head=head, files=files,
                scope='tracked paths at exact HEAD; path-name filter only',
                omissions='No untracked/ignored/runtime/cache contents; code mode omits historical evidence except registered executable dependencies. Not a full-repository search or validation.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--base')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--task')
    parser.add_argument('--head')
    args = parser.parse_args()
    if not args.base or not args.head:parser.error('base and head required')
    if args.check:
        if not args.task:parser.error('task required for execution')
        sys.exit(check(args.root,args.base,args.head,args.task))
    print(json.dumps(scope(args.root, args.base, args.head), ensure_ascii=False))
