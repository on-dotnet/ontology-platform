# G3-M3：arm64 canonical 验收制品传递审批（APPROVED）

人类于2026-10-28本会话明确回复“批准上述精确范围”。仅批准下列Action精确SHA、PUBLIC免费标准arm64 runner、手动任务、≤512MiB/1天传递及无付费/镜像发布/token权限扩展。启用前仍须落实严格费用/归档/事件门禁；此前cache审批与本审批分别记录。

## 已发生阻断

Mac最终canonical冷构建369.176秒，两固定Apache源各180秒超时；已批准精确FROM的Docker pull另在180秒超时，本地镜像数11不变。禁止重启Docker/改系统proxy/放宽摘要/使用旧镜像伪装新canonical。现有PG/Jena测试可复用旧已校验镜像，但正式AppHost仍须取得当前输入身份的新canonical。

## 具体申请

- 唯一新外部Action：GitHub官方MIT `actions/upload-artifact` v7.0.2，固定commit `cf430e030ddbb5b0abf93d22962f4752f3646cd9`；Node24。tag经GitHub官方API及签名提交页交叉核对，精确commit LICENSE为MIT，action.yml已读。
- 只在本PUBLIC仓库手动触发一个`ubuntu-24.04-arm`标准runner job，原生构建已批准Dockerfile、Jena版本/SHA512和FROM摘要；不使用QEMU/新镜像/新包，不安装系统工具。
- 只上传通过canonical严格校验的`image.tar`及`receipt.json`到仓库Actions artifact，总计不超过512MiB，一次保留一个传递制品、retention1天、禁止隐藏文件；不上传源码私有runtime/PFX/env/凭证/卷数据。
- 本仓库PUBLIC标准runner免费政策已按官方文档核对；仅使用当前已含免费服务。若仓库改私有、容量或费用状态无法确认，禁止上传并报告。不得购买容量、改账单/预算、使用larger runner或付费服务。
- 工作流权限仍仅`contents: read`，不加packages/write、不发布GHCR或其它registry、不授予镜像发布权限。Actions artifact可由有仓库访问权限的登录用户下载，公共仓库内容不承诺保密。
- 本机通过已有GitHub连接器下载该精确Run/artifact；核对artifact摘要、producerHead、全部输入/平台/档案hash，再由canonical验证和load。取得后执行真实Mac验证；临时传递artifact届时或1天后清理。不是最终Review ZIP。

## 已批准工作流草案（实际实现及门禁以提交文件为准）

```yaml
name: G3 M3 canonical arm64 transfer
on: workflow_dispatch
permissions:
  contents: read
jobs:
  transfer:
    if: github.event.repository.private == false
    runs-on: ubuntu-24.04-arm
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
      - name: Build and strictly verify canonical transfer
        run: python3 scripts/maintenance/canonical_fuseki.py --task-id G3-M3-001 --run-id transfer-${{ github.run_id }} --platform linux/arm64 --final-gate --export-cache artifacts/fuseki-transfer
      - name: Enforce public bounded exact transfer
        run: |
          python3 - <<'PY'
          import importlib.util,json,os
          from pathlib import Path
          event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
          assert os.environ['GITHUB_EVENT_NAME']=='workflow_dispatch'
          assert os.environ['GITHUB_REPOSITORY']=='on-dotnet/ontology-platform'
          assert event['repository']['full_name']=='on-dotnet/ontology-platform'
          assert event['repository']['private'] is False
          spec=importlib.util.spec_from_file_location('canonical','scripts/maintenance/canonical_fuseki.py')
          canonical=importlib.util.module_from_spec(spec);spec.loader.exec_module(canonical)
          directory=Path('artifacts/fuseki-transfer')
          expected=canonical.identity(Path('infra/development/fuseki'),'linux/arm64')
          receipt=canonical.validate_archive(directory,expected)
          assert receipt['producerHead']==os.environ['GITHUB_SHA']
          size=sum(path.stat().st_size for path in directory.iterdir())
          assert size<=512*1024*1024
          print(json.dumps({'publicOnly':True,'boundedBytes':size,'producerHead':receipt['producerHead']}))
          PY
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9
        with:
          name: canonical-fuseki-arm64-${{ github.sha }}
          path: artifacts/fuseki-transfer
          retention-days: 1
          include-hidden-files: false
          if-no-files-found: error
```

## 官方核验来源

- [精确tag](https://api.github.com/repos/actions/upload-artifact/git/ref/tags/v7.0.2)
- [精确MIT许可](https://raw.githubusercontent.com/actions/upload-artifact/cf430e030ddbb5b0abf93d22962f4752f3646cd9/LICENSE)
- [精确Action声明](https://raw.githubusercontent.com/actions/upload-artifact/cf430e030ddbb5b0abf93d22962f4752f3646cd9/action.yml)
- [PUBLIC标准arm64 runner](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Actions免费使用及存储边界](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
