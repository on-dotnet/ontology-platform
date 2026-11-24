---
name: verify
description: 按改动范围确定并运行本仓库必须的验证命令（test-api、test-web、界面走查），最后以门禁 ./dev.ps1 ci -Report 收尾，贴出实际输出。提交前、开 PR 或转为可评审前、/need 的验证步骤、用户要求"验证一下"时使用。
argument-hint: "[基准分支，默认 origin/main]"
---

# verify：按改动范围验证

## 1 确定改动范围

基准默认 `origin/main`，参数可覆盖：$ARGUMENTS

```powershell
git fetch origin
git diff --name-only origin/main...HEAD
git status --short
```

已提交、未提交、未跟踪的文件都算改动。

## 2 开发中：只跑受影响的测试

| 改动 | 命令 |
| --- | --- |
| `backend/` | `./dev.ps1 test-api tests/<受影响的文件>.py`（可写多个文件；改了被很多测试用到的代码，如 `conftest.py`、`support.py`、迁移，就交给门禁里的全量） |
| `web/` | `./dev.ps1 test-web` |
| 后端接口的请求或响应变了 | `./dev.ps1 gen-api`，再跑 `test-web` |
| `backend/pyproject.toml` 或 `web/package.json` | 先 `./dev.ps1 lock api|web`，再跑对应测试 |
| 页面或组件 | `./dev.ps1 up` 后在浏览器走查（界面规范第 12 节），深浅主题各截一张图 |
| `compose.yaml`、`dev.ps1`、Dockerfile | `./dev.ps1 up` 确认开发栈能起来；测试交给门禁 |

- 同时命中多行就全部运行。
- 不手动跑后端全量 `./dev.ps1 test-api`：全量只在门禁里跑一次。
- 只改纯文档（`docs/`、`*.md`，且不是技能或子代理定义）可以不跑测试，但要说明"未运行测试，原因：纯文档"。

## 3 复审与门禁的顺序

1. 派 `reviewer` 子代理复审，同时运行第 2 节受影响的测试。
2. 有必须修的项就修，修完只跑受影响的测试；第二轮复审只看修改的部分。
3. 复审没有必须修的项之后，提交并推送，对最终 HEAD 运行一次：

```powershell
./dev.ps1 ci -Report
```

门禁要求工作区干净、提交已推送；test-api（全量）、test-web、构建运行镜像三项同时跑，日志在 `.verification/ci/`，失败的一项会打出失败用例和日志末尾。成功后提交状态 `local-ci` 为 success。门禁之后 HEAD 又变了就重新运行。长命令放到后台运行，等完成通知，不轮询。

## 4 汇报

- 每条命令贴出实际输出的结论部分：用例数、失败数、退出码。
- 失败不得跳过、不得重试到碰巧通过就算数：先定位原因，修好后重跑，并说明原因。
- 没有实际运行过的命令写进"未验证项"，不写"已验证"。
