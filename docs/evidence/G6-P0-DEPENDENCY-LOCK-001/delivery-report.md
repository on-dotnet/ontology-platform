# G6-P0-DEPENDENCY-LOCK-001交付报告

G3 main=d1a61daffe844475b07705797e3ad325cc3f2945；G6 PREP=851fa7eb2153c660b7989c0a7a6dd0e1c8e1b63c（未合并）。本轮branch=codex/g6-p0-dependency-lock-001，Base=851fa7eb2153c660b7989c0a7a6dd0e1c8e1b63c，已测试源码commit=46e285b0f762d1a580472e7d394b72dd8548567e。最终交付Head由唯一V3外置Manifest/回执记录，避免自引用。G4仍未启动。

状态PARTIAL / BLOCKED_WITH_WITNESS。下一唯一需用户批准的执行事项：沿用既有pip26.2.2，在任务隔离目录允许有界官方wheel metadata/payload读取，以binary-only dry-run求解；不安装目标包，不包含运行/模型/镜像，细则见locks/install-authorization-draft.md，当前不可执行。uv仅候选登记，许可/无payload能力未知，不捆绑安装。

两平台均54观察包、79声明、57条件wheel候选，未选定任何wheel/solution。Python patch、glibc及镜像digest未冻结。已证doclang0.9.0不满足docling-core<0.9，精确替代0.8.0仅单边满足，不能冒称完整lock。models-local第二轮廓和真实解析/OCR/Docker/模型/API均NOT_RUN。

24定向正反测试与独立非作者复核通过；首次完整工程SelfTest381.7秒exit0，ReviewPackage103/0failure。初始YAML发现缺口的短失败、Reviewer发现跨架构P1与输入边界缺口均原样留证并修复。PREP72测试按29个mode/blob/path复用，不重跑。原HTTP raw字节未存，虽有实际命令/exit/投影stdout/响应测量，原rawhash独立重算仍NOT_VERIFIED。3项许可UNKNOWN，全部native NOTICE/SBOM/安全/模型未验证。

Docker Before/After后端和完整metadata一致，0容器/8卷/13唯一镜像/5history/3network；无创建删除，不推断服务健康。7准确自身临时对象已审并实际清理：6文件42097逻辑bytes+1工具引用symlink，共享target保全；物理回收未知。新任务树/分支保留未集成成果，旧树/旧Docker全部按当前合同保护，准确ID及解除条件见resource-summary.json。当前ignored工作副本待外部复审，ZIP前0、后唯一1，外置回执记录大小/hash。

仅任务分支提交push，CI NOT_RUN，无main合并。固定源码后只更新当前docs/evidence。唯一LOCAL V3(PARTIAL)与非作者独立重开以实际后置回执为准；交付后立即停等ChatGPT复审，不自动推进任何阶段。
