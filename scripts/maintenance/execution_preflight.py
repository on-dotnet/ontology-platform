#!/usr/bin/env python3
"""容器前的有界入口/消费者检查与同输入昂贵失败止损；不安装依赖或启动服务。"""
import argparse
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r'[0-9a-f]{64}\Z')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z')
AUDIT = 'backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs'
MODULE = 'backend/src/Modules/Ontology/OntologyPlatform.Modules.Ontology/OntologyModule.cs'
LAUNCHERS = ('scripts/acceptance/g3-governance.ps1', 'scripts/acceptance/g3-runtime.py',
             'scripts/acceptance/g3-acceptance-runtime.py')


def product_input_fingerprint(root):
    """按实际源码/合同/锁/构建输入字节指纹；说明/过程证据不触发昂贵重验。"""
    root = Path(root).resolve()
    result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                            cwd=root, capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError('INPUT_IDENTITY_UNAVAILABLE: Git输入不可核实')
    digest = hashlib.sha256()
    for relative in sorted(set(result.stdout.decode('utf-8').split('\0'))- {''}):
        if relative in ('AGENTS.md','PLANS.md') or relative.startswith(('docs/evidence/','docs/tasks/','docs/development/')):
            continue
        path = source_path(root, relative)
        if not path.is_file() or path.stat().st_size > 16*1024*1024:
            raise ValueError('INPUT_IDENTITY_INVALID: 输入不是有界普通文件')
        data = path.read_bytes()
        digest.update(relative.encode('utf-8') + b'\0' + str(len(data)).encode('ascii') + b'\0')
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def source_path(root, relative):
    """精确仓库相对路径必须存在，拒绝大小写误配、链接及越界。"""
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('PATH_INVALID: 验收入口必须为仓库相对路径')
    pieces = relative.split('/')
    if any(piece in ('', '.', '..') for piece in pieces):
        raise ValueError('PATH_INVALID: 拒绝空段及目录穿越')
    current = Path(root).resolve()
    for piece in pieces:
        if piece not in {entry.name for entry in current.iterdir()}:
            raise ValueError('PATH_MISSING: 文件或目录不存在或大小写不匹配')
        current = current / piece
        if current.is_symlink():
            raise ValueError('PATH_LINKED: 不跟随验收入口符号链接')
    return current


def check_paths(root, paths):
    """派发前检查准确项目、解释器脚本及目录；无容器副作用。"""
    return [str(source_path(root, item).relative_to(Path(root).resolve())) for item in paths]


def check_cli(command, required_options):
    """仅运行已选择入口的 --help；参数正文与工具输出不进入诊断。"""
    if not command or not all(isinstance(item, str) for item in command):
        raise ValueError('CLI_INVALID: 需要明确可执行入口')
    if not shutil.which(command[0]) and not Path(command[0]).is_file():
        raise ValueError('CLI_MISSING: 解释器不可用')
    try:
        result = subprocess.run([*command, '--help'], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('CLI_UNAVAILABLE: 工具帮助不可核实') from None
    text = result.stdout + result.stderr
    if result.returncode or len(text.encode()) > 1024*1024:
        raise ValueError('CLI_HELP_FAILED: 工具帮助退出失败或超预算')
    for option in required_options:
        if not re.fullmatch(r'--[a-z][a-z0-9-]*', option) or not re.search(r'(?<![\w-])'+re.escape(option)+r'(?![\w-])', text):
            raise ValueError('CLI_OPTION_MISSING: 验收参数未由真实入口支持')
    return True


def uncomment(text):
    """仅供固定登记块检查，去掉注释避免注释中的登记伪装成实际注册。"""
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)


def check_consumers(root, milestone='M5', audit_actions=None, registrations=None):
    """冻结清单核实真实登记块；静态门禁不替代实际 DI resolve 或短真实业务请求。"""
    audit_actions = ['ontology.impact.generate'] if audit_actions is None else audit_actions
    registrations = (['IG3ImpactService', 'IG3ExpressionService', 'IG3ExpressionRuntime']
                     if milestone == 'M5' else ['IG3ImpactService']) if registrations is None else registrations
    text = uncomment(source_path(root, AUDIT).read_text(encoding='utf-8'))
    block = re.search(r'\bActions\s*=\s*new\([^;]*?\)\s*\{(.*?)\};', text, re.S)
    actions = set(re.findall(r'"([a-z][a-z0-9_.]+)"', block[1])) if block else set()
    if any(action not in actions for action in audit_actions):
        raise ValueError('AUDIT_ACTION_MISSING: 消费动作未在真实审计白名单登记')
    module = uncomment(source_path(root, MODULE).read_text(encoding='utf-8'))
    registered = set(re.findall(r'\.Add(?:Scoped|Singleton|Transient)\s*<\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:,|>)', module))
    if any(service not in registered for service in registrations):
        raise ValueError('DI_REGISTRATION_MISSING: 消费服务未在组合入口登记')
    for relative in LAUNCHERS:
        text = source_path(root, relative).read_text(encoding='utf-8')
        if relative.endswith('.ps1'):
            choices = re.search(r'ValidateSet\(([^)]*)\)', text)
            if not choices or milestone not in re.findall(r"'([^']+)'", choices[1]):
                raise ValueError('MILESTONE_GUARD_DRIFT: PowerShell阶段入口不支持当前阶段')
            continue
        tree = ast.parse(text)
        options = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and any(
            isinstance(arg, ast.Constant) and arg.value == '--milestone' for arg in node.args)]
        if not options or not any(any(keyword.arg == 'choices' and milestone in ast.literal_eval(keyword.value)
                                      for keyword in node.keywords) for node in options):
            raise ValueError('MILESTONE_GUARD_DRIFT: Python阶段参数不支持当前阶段')
        if milestone == 'M5' and relative.endswith('g3-acceptance-runtime.py'):
            for node in ast.walk(tree):
                if isinstance(node, ast.Compare) and isinstance(node.left, ast.Attribute) and node.left.attr == 'milestone':
                    if any(isinstance(op, ast.NotEq) for op in node.ops) and any(isinstance(value, ast.Constant) and value.value == 'M4' for value in node.comparators):
                        raise ValueError('MILESTONE_GUARD_DRIFT: Diff或Impact仍以单一M4条件阻断当前阶段')
                    for comparison in node.comparators:
                        if isinstance(comparison, (ast.Tuple, ast.List, ast.Set)):
                            values = ast.literal_eval(comparison)
                            if 'M4' in values and ('M2' in values or 'M3' in values) and milestone not in values:
                                raise ValueError('MILESTONE_GUARD_DRIFT: checkpoint或performance仍使用旧阶段集合')
            if '--m5' not in [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]:
                raise ValueError('MILESTONE_DISPATCH_MISSING: 当前阶段没有真实浏览器派发分支')
    downstream = []
    if milestone == 'M5':
        performance = 'scripts/acceptance/performance-baseline.py'
        fault = 'scripts/acceptance/g2-readiness-fault.py'
        tree = ast.parse(source_path(root, performance).read_text(encoding='utf-8'))
        options = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and any(
            isinstance(arg, ast.Constant) and arg.value == '--chain-report' for arg in node.args)]
        if not any(any(key.arg == 'choices' and 'm5-full-e2e.json' in ast.literal_eval(key.value)
                       for key in node.keywords) for node in options):
            raise ValueError('MILESTONE_METRICS_DRIFT: 下游性能汇总未登记当前阶段报告')
        tree = ast.parse(source_path(root, fault).read_text(encoding='utf-8'))
        branches = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == 'startswith'
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == 'prefix']
        if not any(node.args and isinstance(node.args[0], (ast.Tuple, ast.List))
                   and 'g3-m5-' in ast.literal_eval(node.args[0]) for node in branches):
            raise ValueError('MILESTONE_FAULT_DRIFT: 下游故障入口未登记当前准确前缀')
        patterns = [node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == 'fullmatch'
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str) and node.args[0].value.startswith('g3-m')]
        if not any(re.fullmatch(pattern, 'g3-m5-0123456789ab') and not re.fullmatch(pattern, 'g3-m6-0123456789ab') for pattern in patterns):
            raise ValueError('MILESTONE_FAULT_DRIFT: 故障入口精确阶段正则遗漏或越界')
        downstream = [performance, fault]
    return dict(status='PASS', milestone=milestone, auditActions=audit_actions,
                registrations=registrations, checkedConsumers=list(LAUNCHERS)+downstream,
                limitation='静态消费者门禁，不替代实际组合根、事务回滚或产品请求。')


def ordinary(path):
    """失败状态仅接受有界普通文件，不读取秘密或跟随链接。"""
    target = Path(os.path.abspath(path))
    if any(item.is_symlink() for item in [target, *target.parents]):
        raise ValueError('FAILURE_STATE_LINKED: 拒绝链接')
    if target.exists() and (not target.is_file() or target.stat().st_size > 1024*1024):
        raise ValueError('FAILURE_STATE_INVALID: 状态文件超界')
    return target


class FailureState:
    """准确输入/构建/平台失败记录；持锁覆盖命令，防并发重复昂贵执行。"""
    def __init__(self, path, input_hash, test_build_id, test_build_version, error_category='COMMAND_FAILED'):
        if not SHA.fullmatch(input_hash) or not SHA.fullmatch(test_build_version) or not LABEL.fullmatch(test_build_id) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', error_category):
            raise ValueError('FAILURE_IDENTITY_INVALID: 需要精确输入、构建版本及错误类别')
        self.path = ordinary(path)
        self.identity = dict(inputFingerprint=input_hash, testBuildId=test_build_id,
                             testBuildVersion=test_build_version, platform=platform.system()+'-'+platform.machine(),
                             errorCategory=error_category)
        self.fingerprint = hashlib.sha256(json.dumps(self.identity, sort_keys=True).encode()).hexdigest()
        self.lock = ordinary(str(self.path)+'.lock')
        self.records = []
        self.locked = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError('FAILURE_STATE_BUSY: 已有运行占用该失败状态，禁止并发昂贵重验') from None
        os.close(descriptor)
        self.locked = True
        try:
            if self.path.exists():
                value = json.loads(self.path.read_text(encoding='utf-8'))
                if set(value) != {'schemaVersion','failures'} or value['schemaVersion'] != 1 or not isinstance(value['failures'],list) or len(value['failures']) > 1000:
                    raise ValueError('FAILURE_STATE_INVALID: 失败状态格式失效')
                for row in value['failures']:
                    if set(row) != set(self.identity) | {'failureFingerprint','shortReproduced','observedAtUtc'} or type(row['shortReproduced']) is not bool:
                        raise ValueError('FAILURE_STATE_INVALID: 失败指纹格式失效')
                    fields = {key:row[key] for key in self.identity}
                    if hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest() != row['failureFingerprint']:
                        raise ValueError('FAILURE_STATE_INVALID: 指纹与输入不符')
                self.records = value['failures']
            return self
        except Exception:
            self.__exit__(None,None,None)
            raise

    def allow(self, cost):
        """未变昂贵失败先短复现；仍失败时不允许用新 Run 或标签绕过。"""
        if not self.locked or cost not in ('short','expensive'):
            raise ValueError('FAILURE_GUARD_INVALID: 需要锁内明确执行成本')
        found = next((row for row in self.records if row['failureFingerprint']==self.fingerprint),None)
        if cost == 'expensive' and found is not None:
            code = 'UNCHANGED_FAILURE_BLOCKED' if found['shortReproduced'] else 'SHORT_REPRO_REQUIRED'
            raise ValueError(code+': 相同输入/构建/平台先定位或改变输入，不重复昂贵执行')

    def record(self, cost, exit_code):
        """只保存固定元数据；短复现成功可解除旧候选，失败不覆写真实子进程结果。"""
        if not self.locked or cost not in ('short','expensive') or type(exit_code) is not int:
            raise ValueError('FAILURE_GUARD_INVALID: 需要真实退出码')
        self.records = [row for row in self.records if row['failureFingerprint'] != self.fingerprint]
        if exit_code != 0:
            self.records.append(dict(**self.identity, failureFingerprint=self.fingerprint,
                                     shortReproduced=cost=='short', observedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat()))
        if len(self.records)>1000:
            raise ValueError('FAILURE_STATE_BUDGET: 失败状态数量超限，需人工定位')
        temporary = ordinary(str(self.path)+'.partial')
        created = False
        try:
            with temporary.open('x',encoding='utf-8') as stream:
                created = True
                json.dump(dict(schemaVersion=1,failures=self.records),stream,sort_keys=True)
                stream.write('\n');stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.path)
        finally:
            if created and temporary.exists():temporary.unlink()

    def __exit__(self, exc_type, exc, traceback):
        if self.locked:
            self.lock.unlink()
            self.locked=False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    check=sub.add_parser('check');check.add_argument('--root',type=Path,default=ROOT)
    check.add_argument('--milestone',choices=['M1','M2','M3','M4','M5'],default='M5')
    check.add_argument('--path',action='append',default=[])
    run=sub.add_parser('run')
    for key in ('state','input-hash','test-build-id','test-build-version'):
        run.add_argument('--'+key,required=True)
    run.add_argument('--error-category',default='COMMAND_FAILED');run.add_argument('--cost',choices=['short','expensive'],required=True)
    run.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    try:
        if args.mode=='check':
            check_paths(args.root,args.path)
            result = check_consumers(args.root,args.milestone)
            for relative, options in ((LAUNCHERS[1], ['--milestone','--runtime-file']),
                                      (LAUNCHERS[2], ['--milestone','--runtime-file','--api-only','--ui-only'])):
                check_cli([sys.executable,str(source_path(args.root,relative))],options)
            result['cliHelpVerified'] = list(LAUNCHERS[1:])
            print(json.dumps(result,ensure_ascii=False,sort_keys=True))
            return 0
        target=ordinary(args.state)
        if not target.is_relative_to(Path.cwd().resolve()/'artifacts'):
            raise ValueError('FAILURE_STATE_BOUNDARY: 失败状态必须位于本任务ignored artifacts目录')
        command=args.command[1:] if args.command[:1]==['--'] else args.command
        if not command:raise ValueError('CLI_INVALID: 需要明确命令')
        with FailureState(target,args.input_hash,args.test_build_id,args.test_build_version,args.error_category) as state:
            state.allow(args.cost)
            try:
                result=subprocess.run(command,shell=False).returncode
            except OSError:
                result=127
            state.record(args.cost,result)
            return result if result>=0 else 1
    except (ValueError,OSError,KeyError,TypeError,SyntaxError,json.JSONDecodeError) as failure:
        message=str(failure) if isinstance(failure,ValueError) and re.match(r'^[A-Z_]+:',str(failure)) else 'PREFLIGHT_INVALID: 入口或格式不可核实'
        print('REFUSED: '+message,file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
