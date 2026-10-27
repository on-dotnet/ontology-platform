# 第二真实纵向检查点

Head=903e08b3bf9e52dc4bf69068806cb722fd8e79ac，run=16059b5b39e94283ba223e6c0b8ec762，复用本任务准确g3-m2-8fb61910c7c7 Synthetic卷，未触碰旧G2环境。

命令PLATFORM_EVIDENCE_DIR=docs/evidence/G3-M2-001/runtime/point2 PLATFORM_TASK_ID=G3-M2-001 python3 scripts/acceptance/g3-acceptance-runtime.py --milestone M2 --ui-only --runtime-file .tools/security/g3-m2-8fb61910c7c7/runtime.json --start-runtime，exit0。29真实OIDC/API检查PASS，内部19项包含UI类声明/命名公理真实写入、独立GET revision/hash、其他三源原字节、键盘Enter、1440/390深浅主题及无横向溢出。UI_ONLY1gate，launcher停止exit0；发布/正式查询/回滚及另外6门禁NOT_RUN，留最终full入口。

两次早集成在不同已提交Head先后完成（先SEM/API、后WEB/UI）。Main增量集成因三个旧canonicalCI检查点RUN超时保持BLOCKED，未把失败CI成果合入main；环境修复后必须实际同Head双job成功，回执保留这些历史失败。后续最终稳定检查点及V3预检包/业务门禁另验，不将当时未知改成PASS。
