# M0 平台支持与验收矩阵

记录日期2026-10-25。OBSERVED只代表当前命令实际观察；历史Windows结果保留其原日期；Docker容器平台不等于开发宿主平台。逐项实际结果，最终判定见delivery-report和validation.json。

| 项 | macOS27.0.1 arm64 | Windows x64 | Ubuntu24.04 x64 |
|---|---|---|---|
| Git/gh/Codex/PowerShell | OBSERVED：Git2.56.0、gh2.103.2、Codex0.164.0-alpha.11.1、PS7.6.8 | M0 NOT_RUN；保留G1历史 | CI实际使用Git/PS；Codex客户端NOT_RUN |
| SDK10.0.402/Node24.22.1 | 实际版本匹配 | M0 NOT_RUN | SDK由现有setup-dotnet与global.json锁定；Node原生产品检查NOT_RUN |
| pnpm11.28.8 | PASS：官方SHA512匹配，项目cjs运行11.28.8；全局12.15.0保留 | M0 NOT_RUN；固定目标保留 | Web尚无实际目标，NOT_RUN |
| PyYAML6.0.3重复恢复 | PASS：cp313 arm64官方wheel SHA256及--require-hashes真实恢复 | 保留cp313 x64 hash；M0 NOT_RUN | 保留cp312 x64 hash，实际CI恢复 |
| 自定义角色/独立Worktree | OBSERVED：explorer/worker/reviewer派发、2并行专项、3托管树 | 不复制私有会话/树；M0 NOT_RUN | 客户端NOT_RUN |
| 静态/脚本/ZIP正反例 | A49项及Reviewer复验PASS；Master最终组合复验exit0 | M0 NOT_RUN，原路径字面值兼容审查 | 3ca9c971实际CI success，最终头另按实际run |
| locked restore/build/MTP/format | 独立命令及Reviewer均PASS；MTP4/4/0跳过 | 原win-x64锁逐字节保留；M0 NOT_RUN | 原linux-x64锁保留，CI受锁构建/4项MTP/format |
| SelfTest+RunNative组合 | PASS：保留原FAIL证据，修复unset/empty恢复后完整组合exit0 | 未运行，不外推通过 | 现有CI分进程入口通过，不代表组合入口通过 |
| Docker镜像平台 | 四固定index提供linux/arm64，实际四容器原生运行 | M0 NOT_RUN | 镜像提供linux/amd64；本轮Linux容器运行NOT_RUN |
| AppHost/健康/回环/网络 | PASS：Master直接复验原始stdout与快照；原始运行证据已独立审查通过 | G1历史通过，M0 NOT_RUN | CI不启动容器，NOT_RUN |
| 开发探针重启持久化 | PASS：Master复验四资源标记保持，原始输出已归档 | G1历史通过，M0 NOT_RUN | NOT_RUN |
| Dashboard API Trace检索 | PASS：Master复验401负例及认证200，实际Trace JSON匹配 | M0 NOT_RUN | NOT_RUN |
| Intel Mac / Linux ARM开发宿主 | NOT_RUN，无osx-x64/linux-arm64工程锁验收，不宣称支持通过 | Windows ARM亦NOT_RUN | Linux ARM64容器不代替宿主验收 |
| 生产/SEC/FE/OBS/G2 | NOT_RUN，未授权 | NOT_RUN | NOT_RUN |

CI历史的cancelled为Master连续里程碑push触发现有concurrency取消，不能当PASS。最终main的run ID/URL/head/conclusion由构包runtimeCi绑定，避免已提交报告自引用SHA。没有新增收费macOS Runner。未跑Windows或其他平台不能改写为PASS，整体兼容覆盖保留PARTIAL。
