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

## 2 必须运行的命令

| 改动 | 命令 |
| --- | --- |
| `backend/` | `./dev.ps1 test-api` |
| `web/` | `./dev.ps1 test-web` |
| 后端接口的请求或响应变了 | `./dev.ps1 gen-api`，再跑 `test-web` |
| `backend/pyproject.toml` 或 `web/package.json` | 先 `./dev.ps1 lock api|web`，再跑对应测试 |
| 页面或组件 | `./dev.ps1 up` 后在浏览器走查（界面规范第 12 节），深浅主题各截一张图 |
| `compose.yaml`、`dev.ps1`、Dockerfile | `./dev.ps1 up` 确认开发栈能起来，再跑 `test` |

- 同时命中多行就全部运行。
- 只改纯文档（`docs/`、`*.md`，且不是技能或子代理定义）可以不跑测试，但要说明"未运行测试，原因：纯文档"。

## 3 以门禁收尾

提交并推送之后，对当前 HEAD 运行：

```powershell
./dev.ps1 ci -Report
```

门禁要求工作区干净、提交已推送；成功后提交状态 `local-ci` 为 success。HEAD 变化后要重新运行。长命令放到后台运行，等完成通知，不轮询。

## 4 汇报

- 每条命令贴出实际输出的结论部分：用例数、失败数、退出码。
- 失败不得跳过、不得重试到碰巧通过就算数：先定位原因，修好后重跑，并说明原因。
- 没有实际运行过的命令写进"未验证项"，不写"已验证"。
