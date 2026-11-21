"""本批产品资源准入：只核销已实际删除的基线缓存，不修改原审计依赖。"""
import ast
from types import CodeType
from pathlib import Path
import workflow_execution as ex
import workflow_oracle_mapping_resources as original_resources
import workflow_oracle_mapping_platform as original_platform
from workflow_oracle_mapping_resources import *
from workflow_oracle_mapping_platform import MEASURE_TREE, VOLUMES, current_storage, backup_allocation

PRODUCT='product-resume-01'
ENVIRONMENT='d6d909b8cad6e0c13389a3323def278aa77870bbca92689ade15af303daafb43'
ORIGINAL_CALL="    return before_source(ROOT,TASK,platform_stage=True,phase=PRODUCT,running_roles=active,planned_roles=active|set(planned))\n"
PRODUCT_CALL="    from workflow_oracle_mapping_capacity import before_product_source\n    return before_product_source(ROOT,TASK,platform_stage=True,phase=PRODUCT,running_roles=active,planned_roles=active|set(planned))\n"
LEDGERS=(
 ('cache-reclamation-161220a07b1d41568c3179577c1d218d.json','28e905e5b1ee5e2b0d2f846f766b40aa320d68e4339ebb242f8183790cdfedfe','s23-reclaim-two-public-feed-copies'),
 ('cache-reclamation-e0a7b7e1510a4e47a4fc606fa35af880.json','d443c21c3233b3af12f86ed21634d6fad641108ed3aae185dbe33166a848d429','s23-reclaim-nine-public-feed-copies'),
 ('cache-reclamation-c158243e3fc145439b46e6df983316cc.json','99b33e3f7bdb91975ad06201a601df9d302332963ddc73b64375226642bdac7a','s23-reclaim-fifty-two-public-feed-copies'))


def baseline_cache_release(root,area):
    """原准备早于真实基线du；只计仍缺席的63准确公共副本，重现逐项撤销信用。"""
    import workflow_oracle_mapping_continuity as c
    from workflow_oracle_mapping_evidence import utc
    require(area==root/'artifacts/workflow'/TASK/RUN,'CAPACITY_BASELINE_SCOPE')
    planned=json.loads(ex.ordinary(area/'formal-planned.json').read_bytes())
    require((planned['taskId'],planned['runId'],planned['resourceAttempt'])==(TASK,RUN,'494170ac92db477b80201a7c44670ec3'),'CAPACITY_BASELINE_SELECTED')
    baseline=ex.ordinary(area/'source-admission-494170ac92db477b80201a7c44670ec3.json').read_bytes()
    require(ex.sha(baseline)=='319016ff62c8edc28687de7519819195d83e6a9ac6d686cc3d3c6ba2fcaf67ae','CAPACITY_BASELINE_ORIGINAL')
    basis=json.loads(baseline);require(str(root) in basis['platformDisk']['hostPaths'],'CAPACITY_BASELINE_HOST')
    home=area.parent/'environment'/ENVIRONMENT;directory=home/'runs/3463d8ec1a64483989d9f2b531190dbb'
    raw=ex.ordinary(directory/'receipt.json').read_bytes();require(ex.sha(raw)=='f313171378ae6921744c90136c87f9857856bf708265ce6a337015163b472e43','CAPACITY_PREPARE_ORIGINAL')
    prepared=json.loads(raw);require(prepared['materializedFiles']==727 and prepared['restoreCount']==1 and prepared['downloads']==prepared['sdkDownloads']==0,'CAPACITY_PREPARE_SCOPE')
    restored=json.loads(ex.ordinary(directory/'restore.json').read_bytes())
    from workflow_environment import locks
    _,projects,_=locks(root);require(len(projects)==prepared['projects'],'CAPACITY_RESTORE_PROJECTS')
    writable=[home,*[root/Path(p['path']).parent/'obj' for p in projects]]
    profile='(version 1) (allow default) (deny network*) (deny file-write*) (allow file-write* (literal "/dev/null") '+ ' '.join('(subpath '+json.dumps(str(p))+')' for p in writable)+')'
    argv=['/usr/bin/sandbox-exec','-p',profile,*restored['command']]
    command_dir=area.parent/'commands/3463d8ec1a64483989d9f2b531190dbb/9666009e3cbb4830aef9f19ca4004529'
    command=json.loads(ex.ordinary(command_dir/'receipt.json').read_bytes());streams=[]
    from workflow_oracle_mapping_evidence import summary
    require(command['schemaVersion']==2 and command['taskId']==TASK and command['runId']=='3463d8ec1a64483989d9f2b531190dbb'
        and command['commandId']=='9666009e3cbb4830aef9f19ca4004529' and command['parentId'] is None and command['cwd']==str(root)
        and command['stage']=='restore' and command['started'] and command['signal'] is None and command['exitCode']==0 and command['classification']=='SUCCESS'
        and command['deadlineSeconds']==600 and command['inputFingerprint']==ENVIRONMENT and command['commandSummary']==summary(argv)
        and command['environmentFingerprint']==ex.sha(ex.encoded(prepared['environment']))
        and command['identity']==ex.sha(ex.encoded([ENVIRONMENT,command['environmentFingerprint'],ex.sha(ex.encoded(['restore',restored['command']])),str(root),600,ex.sha((root/'scripts/maintenance/workflow_execution.py').read_bytes())])), 'CAPACITY_RESTORE_COMMAND')
    for kind in ('stdout','stderr'):
        data=ex.ordinary(command_dir/(kind+'.txt')).read_bytes();require(command[kind]['path']==str(command_dir/(kind+'.txt')) and command[kind]['sha256']==ex.sha(data) and command[kind]['sizeBytes']==len(data),'CAPACITY_RESTORE_STREAM');streams.append(data)
    out,err=streams
    require(ex.sha(out+err)==restored['outputSha256'] and utc(command['endedAtUtc'])<utc(basis['startedUtc']),'CAPACITY_BEFORE_BASELINE')
    seen=set();credit=0;reappeared=[];proofs=[];total=0
    for filename,digest,stage in LEDGERS:
        path=area.parent/PRODUCT/'s2-s3-01'/filename;raw=ex.ordinary(path).read_bytes();require(ex.sha(raw)==digest,'CAPACITY_RELEASE_ORIGINAL');row=json.loads(raw)
        require((row['taskId'],row['runId'],row['batch'],row['status'])==(TASK,PRODUCT,'s2-s3-01','REMOVED_VERIFIED') and row['after']['absent']
            and row['creation']['receiptSha256']==ex.sha(ex.ordinary(directory/'receipt.json').read_bytes()),'CAPACITY_RELEASE_SCOPE')
        items=row['before']['files'];argv=['/bin/rm','--',*[item['path'] for item in items]]
        removed,out,err=c.command(root,row['command']['commandId'],PRODUCT,argv,stage,ex.sha(ex.encoded(row['before'])),30)
        require(not out and not err and utc(basis['endedUtc'])<utc(removed['startedAtUtc']),'CAPACITY_REMOVE_COMMAND')
        for item in items:
            target=ex.ordinary(Path(item['path']));require(target.parent==home/'feed' and target.suffix=='.nupkg' and target not in seen,'CAPACITY_CACHE_PATH');seen.add(target)
            require(type(item['allocatedBytes']) is int and item['sizeBytes']<=item['allocatedBytes']<item['sizeBytes']+4096,'CAPACITY_ALLOCATION')
            copies=[Path(p) for p in item['reusableCopies']]
            # 后续已准许回收本树压缩副本时，允许同批准包身份的准确global原档继续作为恢复来源。
            first=copies[0];require(first.is_relative_to(home/'nuget-packages') and first.name==target.name,'CAPACITY_COPY_SCOPE')
            relative=first.relative_to(home/'nuget-packages');copies.append(Path('/Users/chasen/.nuget/packages')/relative)
            valid=[p for p in copies if p.is_file() and not p.is_symlink() and p.stat().st_size==item['sizeBytes'] and ex.sha(ex.ordinary(p).read_bytes())==item['sha256']]
            require(valid,'CAPACITY_RETAINED_COPY');total+=item['allocatedBytes']
            if target.exists() or target.is_symlink():reappeared.append(target.name)
            else:credit+=item['allocatedBytes']
        proofs.append(dict(file=filename,sha256=digest,commandId=row['command']['commandId']))
    require(len(seen)==63 and total==254558208 and 0<=credit<=total,'CAPACITY_RELEASE_TOTAL')
    return dict(releasedBytes=credit,original63AllocatedBytes=total,paths=63,reappeared=reappeared,proofs=proofs,
        scope='Subtract only from original host_start; measured host and total receive no further subtraction; full prepare NOT_CURRENT')


def validate_programs():
    """复制入口逐节点与原函数一致，且每个原全局绑定相同；仅允许列明的产品准入变化。"""
    here=ast.parse(Path(__file__).read_bytes())
    for new_name,old_module,old_name in [('before_product_source',original_resources,'before_source'),('disk_admission',original_platform,'disk_admission')]:
        old_tree=ast.parse(Path(old_module.__file__).read_bytes());old=next(n for n in old_tree.body if isinstance(n,ast.FunctionDef) and n.name==old_name)
        new=next(n for n in here.body if isinstance(n,ast.FunctionDef) and n.name==new_name);new.name=old_name
        expected=ast.parse("validate_programs()\nrequire(phase=='product-resume-01','CAPACITY_PRODUCT_ONLY')").body
        require([ast.dump(n,include_attributes=False) for n in new.body[1:3]]==[ast.dump(n,include_attributes=False) for n in expected],'CAPACITY_ENTRY_GUARDS')
        del new.body[1:3]
        if new_name=='before_product_source':
            imports=0
            for node in ast.walk(new):
                if isinstance(node,ast.ImportFrom) and node.module=='workflow_oracle_mapping_capacity':
                    require([(a.name,a.asname) for a in node.names]==[('disk_admission',None)],'CAPACITY_IMPORT_SCOPE');node.module='workflow_oracle_mapping_platform';imports+=1
            require(imports==2,'CAPACITY_IMPORT_COUNT')
        else:
            expected=ast.parse("cache_release=baseline_cache_release(root,area)\nhost_start-=cache_release['releasedBytes']").body
            indices=[i for i,n in enumerate(new.body) if ast.dump(n,include_attributes=False)==ast.dump(expected[0],include_attributes=False)]
            require(len(indices)==1,'CAPACITY_CREDIT_LOCATION');index=indices[0]
            require(ast.dump(new.body[index+1],include_attributes=False)==ast.dump(expected[1],include_attributes=False),'CAPACITY_CREDIT_ONCE');del new.body[index:index+2]
            # 只允许批次决定替换末端比较值与回执上限，其余逐节点和全局绑定继续验证。
            end = ast.parse("from workflow_oracle_runtime_window import ceiling\nlimit = ceiling(total)\nrequire(total<=limit,'FORMAL_TOTAL_DISK_'+str(total))").body
            require([ast.dump(n) for n in new.body[-4:-1]] == [ast.dump(n) for n in end], 'CAPACITY_LIMIT_SELECTION')
            new.body[-4:-1] = ast.parse("require(total<=40*GIB,'FORMAL_TOTAL_DISK_'+str(total))").body
            kw = [k for k in new.body[-1].value.keywords if k.arg == 'ceilingBytes']
            require(len(kw) == 1 and ast.unparse(kw[0].value) == 'limit', 'CAPACITY_RECEIPT_LIMIT')
            kw[0].value = ast.parse('40*GIB', mode='eval').body
            returned=new.body[-1];require(isinstance(returned,ast.Return) and isinstance(returned.value,ast.Call),'CAPACITY_RETURN')
            found=[k for k in returned.value.keywords if k.arg=='releasedBaselineCache'];require(len(found)==1 and ast.unparse(found[0].value)=='cache_release','CAPACITY_RETURN_CREDIT')
            returned.value.keywords.remove(found[0])
        require(ast.dump(new,include_attributes=False)==ast.dump(old,include_attributes=False),'CAPACITY_PROGRAM_CHANGED')
        original=getattr(old_module,old_name)
        pending=[original.__code__]
        while pending:
            code=pending.pop();pending.extend(value for value in code.co_consts if isinstance(value,CodeType))
            for key in code.co_names:
                if key in original.__globals__:require(globals().get(key) is original.__globals__[key],'CAPACITY_GLOBAL_BINDING_'+key)



def before_product_source(root, task, source_id=None, *, platform_stage=False, phase=None, running_roles=(), planned_roles=None):
    """创建前及运行时核对当前准入；运行时只容许已记录的准确源 ID。"""
    validate_programs()
    require(phase=='product-resume-01','CAPACITY_PRODUCT_ONLY')
    require(task == TASK, 'TASK')
    area = ordinary(root/'artifacts/workflow'/task)
    from workflow_oracle_mapping_recovery_components import BATCH, PHASES, EXTRA
    components=phase in PHASES
    resume = phase == 'product-resume-01'
    stage_run=phase if resume else BATCH if components else ('s0-recovery-01' if phase else RUN)
    require(not phase or (platform_stage and source_id is None), 'RECOVERY_STAGE')
    stamp = uuid.uuid4().hex
    record = dict(taskId=task, runId=stage_run, resourceRunId=RUN, phase=phase, attempt=stamp, status='STARTED', commands=[],
                  startedUtc=dt.datetime.now(dt.timezone.utc).isoformat())
    path = area/stage_run/('source-admission-' + stamp + '.json')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def command(stage, argv, cleanup=False):
        result = run(argv, root, task=task, run_id=stage_run, stage='oracle-admission-' + stage,
                     timeout=18, diagnostic=True, cleanup=cleanup)
        record['commands'].append(dict(stage=stage, commandId=result.receipt['commandId'],
                                       exitCode=result.returncode, stdout=result.receipt['stdout'], stderr=result.receipt['stderr']))
        require(result.returncode == 0, stage)
        return result.stdout.decode().strip()

    def docker(stage, *args, cleanup=False):
        return command(stage, ['docker', '--context', 'desktop-linux', *args], cleanup)

    try:
        original = ordinary(area/'resource-inventory.json').read_bytes()
        require(sha(original) == INVENTORY_SHA, 'P0_INVENTORY')
        expected = json.loads(original)['retained']
        keep = [row.split('|') for row in expected]
        require(command('context', ['docker', 'context', 'show']) == 'desktop-linux', 'CONTEXT')
        current = docker('old-resources', 'inspect', '-f', KEEP_FORMAT, *[row[0] for row in keep]).splitlines()
        require(current == expected, 'RETAINED_DRIFT')
        running = [row for row in keep if row[2] == 'running']
        accounted = {r[0] for r in running}
        if source_id is not None:
            created = json.loads(ordinary(area/RUN/'source-create-01.json').read_bytes())
            require(created['taskId'] == task and created['runId'] == RUN, 'SOURCE_OWNER')
            volume = created['volume']
            if source_id != created['containerId']:
                replacement = json.loads(ordinary(area/RUN/'recovery-01-resume.json').read_bytes())
                require(replacement['taskId'] == task and replacement['runId'] == RUN and replacement['originalId'] == created['containerId']
                        and replacement['replacementId'] == source_id and replacement['status'] == 'NATIVE_RESTORED_PENDING_DRIVER', 'REPLACEMENT_OWNER')
                require(docker('offline-original', 'inspect', '-f', '{{.State.Status}}', created['containerId']) == 'exited', 'RECOVERY_OVERLAP')
                volume = replacement['replacementVolume']
            row = docker('warm-source','inspect','-f','{{.Id}}|{{.Image}}|{{index .Config.Labels "ontology.task"}}|{{index .Config.Labels "ontology.run"}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{range .Mounts}}{{.Name}}{{end}}',source_id).split('|')
            require(row == [source_id, SOURCE.split('@')[1], task, RUN, str(4*GIB), '2000000000', volume], 'SOURCE_DRIFT')
            accounted.add(source_id)
        platform_memory = 0
        held_ports = set()
        if phase:
            from workflow_oracle_mapping_platform_recovery import phase_inventory
            if resume:
                from workflow_oracle_mapping_resume import inspect_product_stage
                known,platform_memory,platform_cpu,held_ports,replacement=inspect_product_stage(area/RUN,running_roles,docker)
            elif components:
                from workflow_oracle_mapping_recovery_components import inspect_stage
                known,platform_memory,platform_cpu,held_ports,replacement=inspect_stage(area/RUN,phase,running_roles,docker)
            else:
                known,platform_memory,platform_cpu,held_ports,replacement=phase_inventory(area/RUN,phase,running_roles,docker)
            accounted.update(known)
            from workflow_oracle_mapping_platform import QUOTAS
            from workflow_oracle_mapping_platform_recovery import ORIGINAL_IDS
            upcoming=set(running_roles if planned_roles is None else planned_roles)
            require(upcoming<=(PHASES[phase] if components else set(ORIGINAL_IDS) | ({'api','api-secondary'} if resume else set())) and (phase!='closed' or not upcoming),'PLANNED_ROLE')
            pending_roles=upcoming-set(running_roles)
            quotas={**QUOTAS,'oracle':(4096,2),**EXTRA}
            next_memory=platform_memory+sum(quotas[n][0]*1024**2 for n in pending_roles)
            next_cpu=platform_cpu+sum(int(quotas[n][1]*1e9) for n in pending_roles)
            record['projectedWithHelper']={'memory':4*GIB+next_memory,'nanoCpus':4_500_000_000+next_cpu}
            record['expectedRunningRoles']=sorted(running_roles)
            record['activeQuota']={'memory':int(3.5*GIB)+platform_memory,'nanoCpus':4_000_000_000+platform_cpu}
        elif platform_stage:
            from workflow_oracle_mapping_platform import verify_owned_platform
            known, platform_memory, held_ports = verify_owned_platform(area/RUN, docker)
            accounted.update(known)
        require(set(docker('all-running', 'ps', '-q', '--no-trunc').splitlines()) == accounted, 'RUNNING_DRIFT')
        require(len(running) == 3 and len(keep) == 20 and sum(int(r[3]) for r in running) == 7*GIB//2
                and sum(int(r[4]) for r in running) == 4_000_000_000, 'RETAINED_QUOTAS')
        record['protectedOriginalSha256'] = INVENTORY_SHA
        total, cpu, os_name, arch = docker('capacity', 'info', '-f', '{{.MemTotal}} {{.NCPU}} {{.OSType}} {{.Architecture}}').split()
        require(os_name == 'linux' and arch == 'aarch64' and int(total) >= 11*GIB and int(cpu) >= 8, 'VM_CAPACITY')
        stats = command('host-ram', ['vm_stat'])
        page = int(re.search(r'page size of (\d+) bytes', stats)[1])
        counts = {k: int(n) for k,n in re.findall(r'^Pages (free|inactive):\s+(\d+)\.', stats, re.M)}
        require(len(counts) == 2, 'HOST_OBSERVATION')
        host = dict(availableEstimate=page*sum(counts.values()), estimate='free + inactive pages',
                    diskBytes=shutil.disk_usage(root).free, pressure=command('pressure',['memory_pressure','-Q']),
                    swap=command('swap',['sysctl','-n','vm.swapusage']))
        record['host'] = host
        require(host['availableEstimate'] >= 4*GIB and host['diskBytes'] >= 14*GIB, 'HOST_FLOOR')
        available_ports = []
        for port in range(15741, 15748):
            with socket.socket() as sock:
                try:
                    sock.bind(('127.0.0.1', port))
                except OSError:
                    continue
                available_ports.append(port)
        frozen = json.loads((area/RUN/'source-create-01.json').read_bytes())['portMap'] if source_id or phase else None
        if frozen:
            require(set(frozen.values()) <= set(available_ports) | held_ports, 'FROZEN_PORT_COLLISION')
            record['portMap'] = frozen
        else:
            require(len(available_ports) >= 4, 'PORTS')
            record['portMap'] = dict(zip(('api','secondary','oidc','web'),available_ports[:4],strict=True))
        facts = []
        for kind, image in (('source', SOURCE),('probe', PROBE)):
            raw = docker(kind+'-image', 'image','inspect','-f','{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|{{json .RootFS.Layers}}|{{json .RepoDigests}}', image)
            ident, platform, arch, size, layers, digests = raw.split('|')
            require(ident == image.split('@')[1] and image in json.loads(digests) and (platform,arch) == ('linux','arm64'), 'IMAGE_ID')
            facts.append(dict(ref=image,id=ident,bytes=int(size),layers=json.loads(layers)))
        require(facts[0]['bytes'] <= 13*GIB and not set(facts[0]['layers']) & set(facts[1]['layers']), 'SOURCE_LAYER_BUDGET')
        record['sourceStageImages'] = facts
        # 三份 5 GiB 源数据分别对应原卷、冷备和替代恢复，准备缓存与日志另计。
        planned = dict(images=sum(r['bytes'] for r in facts), original=5*GIB, backup=5*GIB,
                       replacement=5*GIB, preparedAndBuild=4*GIB, logsAndEvidence=GIB)
        require(sum(planned.values()) <= 40*GIB, 'DISK_ENVELOPE')
        record['sourceStageDiskPlanBytes'] = planned
        require(docker('probe-volume-declaration','image','inspect','-f','{{json (index .Config "Volumes")}}',PROBE) in ('{}','null'), 'ANONYMOUS_VOLUME')
        if phase:
            from workflow_oracle_mapping_capacity import disk_admission
            record['platformDisk']=disk_admission(root,area/RUN,command,phase=phase,replacement=replacement)
            require(record['projectedWithHelper']['memory']<=int((13.75 if resume else 12.25)*GIB)
                    and record['projectedWithHelper']['nanoCpus']<=(10_500_000_000 if resume else 9_500_000_000)
                    and int(total)>=record['projectedWithHelper']['memory']+3*GIB
                    and int(cpu)*1_000_000_000>=record['projectedWithHelper']['nanoCpus']+1_500_000_000,'RECOVERY_CAPS')
        cid = docker('probe-create','create','--pull=never','--network=none','--read-only','--cap-drop=ALL',
                     '--security-opt=no-new-privileges','--user=65534:65534','--memory=64m','--memory-swap=64m',
                     '--cpus=.25','--pids-limit=16','--label','ontology.task='+task,'--label','ontology.run='+RUN,
                     '--label','ontology.attempt='+stamp,'--entrypoint=/bin/sh',PROBE,'-ec','cat /proc/meminfo /proc/loadavg; df -Pk /')
        require(re.fullmatch('[0-9a-f]{64}',cid), 'PROBE_ID')
        record['probeId'] = cid
        def state(label):
            row = docker(label,'inspect','-f','{{.Id}} {{.Image}} {{index .Config.Labels "ontology.attempt"}} {{len .Mounts}} {{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}',cid).split()
            require(row[:4] == [cid,facts[1]['id'],stamp,'0'], 'PROBE_IDENTITY')
            return row[4:]
        try:
            require(state('probe-before')[0] == 'created','PROBE_PRESTATE')
            raw = docker('probe-start','start','-a',cid)
            require(state('probe-exit') == ['exited','0','false'],'PROBE_EXIT')
        finally:
            require(state('probe-before-release')[0] in ('created','exited'), 'PROBE_RELEASE_STATE')
            docker('probe-remove','rm',cid,cleanup=True)
            require(not docker('probe-after','ps','-aq','--no-trunc','--filter','id='+cid,cleanup=True),'PROBE_REAPPEARED')
            record['probeRemoved'] = True
        vm = dict(total=int(total), cpus=int(cpu), available=int(re.search(r'^MemAvailable:\s+(\d+) kB',raw,re.M)[1])*1024,
                  availableFs=int(raw.splitlines()[-1].split()[-3])*1024,
                  load=next(line for line in raw.splitlines() if re.match(r'^\d+\.\d+ \d+\.\d+',line)))
        record['vm'] = vm
        if phase:
            require(vm['available']>=3*GIB+record['projectedWithHelper']['memory']-record['activeQuota']['memory'],'PROJECTED_VM_FLOOR')
        require(vm['available'] >= (7 if source_id or phase else 15)*GIB//2 and vm['availableFs'] >= 26*GIB, 'VM_FLOOR')
        if platform_stage and not phase:
            from workflow_oracle_mapping_capacity import disk_admission
            require(source_id == created['containerId'] and int(total) >= 16.75*GIB and int(cpu) >= 12, 'FORMAL_PEAK_CAPS')
            # 已在运行的硬配额已计入当前可用量，另扣尚未启动的已授权服务与一次探针。
            pending = max(0, int(13.75*GIB) - int(7.5*GIB) - platform_memory)
            require(vm['available'] >= 3*GIB + pending, 'FORMAL_VM_HEADROOM')
            record['platformDisk'] = disk_admission(root,area/RUN,command)
        record['status'] = 'FORMAL_RESOURCE_READY' if platform_stage else 'SOURCE_STAGE_RESOURCE_READY'
        return record
    except Exception as error:
        record.update(status='BLOCKED',reason=str(error))
        raise
    finally:
        record['endedUtc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        with path.open('x') as output:
            json.dump(record, output, indent=2)
            output.write('\n')


def disk_admission(root,area,command,*,phase=None,replacement=None):
    """统计所有当期工作树、镜像及三份源数据，替代恢复的原盘、备份和副本同时保留。"""
    validate_programs()
    require(phase=='product-resume-01','CAPACITY_PRODUCT_ONLY')
    layer=json.loads((area/'platform-image-layer-closure-01.json').read_bytes())
    require(layer['taskId']==TASK and len(layer['imageSizes'])==6 and len(layer['sharedEmptyLayers'])==3,'IMAGE_CLOSURE')
    # 只有两个相同压缩空层共享；其余已证有界的保守镜像总量全部计费。
    images=layer['deduplicatedImageUpperBytes']
    require(images==sum(layer['imageSizes'])-layer['duplicateCompressedBytes'],'IMAGE_BYTES')
    rec=json.loads((area/'recovery-01.json').read_bytes());reopened=json.loads((area/'recovery-01-final.json').read_bytes())
    require(reopened['status']=='EARLY_SOURCE_RECOVERY_PASS','EARLY_RECOVERY')
    source=rec['allocatedSourceBytes'];host_dirs=[root,MEASURE_TREE]
    all_trees=command('formal-worktrees',['git','worktree','list','--porcelain'])
    for block in all_trees.split('\n\n'):
        lines=block.splitlines()
        if any(line in ['branch refs/heads/codex/omq-source-bindings','branch refs/heads/codex/omq-deadline-store'] for line in lines) or Path(lines[0].removeprefix('worktree ')).parent.name in ('omq-source-bindings','omq-deadline-store'):
            host_dirs.append(Path(lines[0].removeprefix('worktree ')))
    if phase == 'product-resume-01':
        host_dirs.extend(p for p in (Path('/private/tmp/omq-product-resume-observer'), Path('/private/tmp/omq-product-resume-measure-4924')) if p.is_dir())
    host_roots=[p for p in host_dirs if p.is_dir()]
    measurements=[line.split(None,1) for line in command('formal-host-bytes',['du','-sk',*[str(p) for p in host_roots]]).splitlines()]
    require([row[1] for row in measurements]==[str(p) for p in host_roots], 'HOST_MEASUREMENT_SET')
    host=sum(int(row[0])*1024 for row in measurements)
    # 初次完整准入的主机字节已经包含首份备份。之后的构建消费已登记的增长余量。
    initial_record=area/'formal-planned.json'
    host_start=host
    require(not phase or initial_record.is_file(), 'RECOVERY_BASELINE_MISSING')
    if initial_record.exists():
        attempt=json.loads(initial_record.read_bytes())['resourceAttempt']
        previous=json.loads((area/('source-admission-'+attempt+'.json')).read_bytes())['platformDisk']
        host_start=previous['allocations']['currentHostIncludingFirstBackup']
    released=area/'early-checkout-release-01.json'
    if released.exists():
        reduced=json.loads(released.read_bytes())
        require(reduced['checkout']==str(host_dirs[1]) and reduced['beforeBytes']-reduced['afterBytes']==reduced['releasedBytes'],'SPARSE_BASIS')
        host_start-=reduced['releasedBytes']
    cache_release=baseline_cache_release(root,area)
    host_start-=cache_release['releasedBytes']
    # 保留两个卷、两次冷备和已验证的替代卷。最终恢复只写已复核可重建的本任务替代卷。
    usage = current_storage(area, replacement) if phase else current_storage(area)
    basis = json.loads((area/'formal-platform-size-basis.json').read_bytes())
    source_caps = {key: int(4.25*GIB) for key in usage['volumesLogicalBytes']}
    require(len(source_caps)==2 and source<=min(source_caps.values()) and all(
        type(size) is int and size>=0 and (phase or size<=source_caps[name]) for name,size in usage['volumesLogicalBytes'].items()),'OBSERVED_SOURCE_SIZE')
    # 两份同构历史样本各含四项服务数据；另外以三份平台 PG 中的最大值计费。
    samples=[row['bytes'] for row in basis['sourceRawVolumeFacts']]
    require(len(samples)==8 and len(basis['pgVolumeMetadataOnly'])==3,'PLATFORM_SIZE_BASIS')
    sample=max(sum(samples[:4]),sum(samples[4:]))+max(basis['pgVolumeMetadataOnly'].values())
    platform_copy=3*GIB//4
    require(sample*1.5<=platform_copy and sum(usage['platformVolumes'].values())<=platform_copy,'PLATFORM_SAMPLE_GROWTH')
    reserved={'images':images,'sourceAndReplacement':sum(source_caps.values()),
              'containerLayers':sum(usage['containerWritableBytes'].values()),'currentHostIncludingFirstBackup':host,
              'secondColdSourceCopy':int(4.25*GIB),'platformOriginalFirstBackupFinalBackupAndReplacement':platform_copy*4,
              'boundedContainerLogs':16*20*1024**2,'boundedProbeAndStreamingTemporary':64*1024**2,
              'newBuildEvidenceAndLogs':max(64*1024**2,host_start+int(.75*GIB)-host)}
    if phase:
        from workflow_oracle_mapping_recovery_components import BATCH, PHASES
        require(phase in ('preserve','restore','closed','product-resume-01') or phase in PHASES, 'RECOVERY_PHASE')
        require(len(set(host_dirs))==len(host_dirs) and all(p.is_dir() for p in host_dirs), 'RECOVERY_HOST_MEASUREMENT')
        sizes = usage['volumesLogicalBytes']
        original = json.loads((area/'source-create-01.json').read_bytes())['volume']
        require(original in sizes and set(usage['platformVolumes'])==set(VOLUMES), 'RECOVERY_VOLUME_ID')
        # 两个 Oracle 卷均保留。当前原卷大小及归档头部/增长余量同时约束还原卷与新冷备。
        source_limit = max(int(4.25*GIB), sizes[original]+64*1024**2)
        reserved['sourceAndReplacement'] = sum(max(size,source_limit) for size in sizes.values())
        source_credited = backup_allocation(root,area,'source',phase=phase)
        platform_credited = backup_allocation(root,area,'platform',phase=phase)
        require(source_credited+platform_credited<=host, 'ARCHIVES_OUTSIDE_HOST_MEASUREMENT')
        reserved['secondColdSourceCopy'] = max(0,source_limit-source_credited)
        # 原卷、当前检查点和替代卷各有一项。备份实际落盘量已在 host 当中。
        del reserved['platformOriginalFirstBackupFinalBackupAndReplacement']
        reserved['platformOriginal'] = platform_copy
        reserved['platformCheckpointRemaining'] = max(0,platform_copy-platform_credited)
        reserved['platformReplacement'] = max(platform_copy,sum(usage['replacementVolumes'].values()))
        reserved['newBuildEvidenceAndLogs'] = max(64*1024**2,host_start+int(.75*GIB)-(host-source_credited-platform_credited))
        source_caps = {name:max(source_limit,size) for name,size in sizes.items()}
    component_budget=None
    if phase and phase in PHASES:
        start=json.loads((area.parent/BATCH/'disk-start.json').read_bytes())
        require(start['limitIncrement']==64*1024**2 and start['diskPaths']==[str(p) for p in host_dirs],'COMPONENT_DISK_BASIS')
        # 宿主与各容器可写层已经计入原账本，只增加准确参考卷实耗和本批尚未消费的预留。
        base_host=min(start['hostBytes'],start['previousHostBytes'])
        growth=max(0,host-base_host);reference=sum(usage['componentVolumes'].values());layers=sum(usage['componentLayers'].values())
        used=growth+reference+layers
        require(used<=start['limitIncrement'],'COMPONENT_64M_LIMIT_'+str(used))
        remaining=start['limitIncrement']-used
        component_budget=dict(hostGrowth=growth,referenceVolume=reference,componentLayers=layers,used=used,remaining=remaining,limit=start['limitIncrement'])
        reserved['componentReferenceActual']=reference
        transfer=min(remaining,reserved['newBuildEvidenceAndLogs'])
        reserved['newBuildEvidenceAndLogs']-=transfer
        reserved['componentGrowthRemaining']=remaining
    total=sum(reserved.values())
    from workflow_oracle_runtime_window import ceiling
    limit = ceiling(total)
    require(total<=limit,'FORMAL_TOTAL_DISK_'+str(total))
    return dict(releasedBaselineCache=cache_release,allocations=reserved,componentBudget=component_budget,totalBytes=total,ceilingBytes=limit,hostPaths=[str(p) for p in host_dirs],
                representativePlatformBytes=sample,platformCopyCeiling=platform_copy,
                sourceVolumeCaps=source_caps,initialSourceMeasurement=usage,
                measuredAgainBeforeExpansionOrRestore=True)
