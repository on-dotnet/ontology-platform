# 两次早集成检查点

point1 Head=36b0f39b4fc73895e0f516da49496f255c579b1c，run=e7f212fefa41428395ed645879de4872，volumePrefix=g3-m2-8fb61910c7c7。命令PLATFORM_EVIDENCE_DIR=docs/evidence/G3-M2-001/runtime/point1 PLATFORM_TASK_ID=G3-M2-001 python3 scripts/acceptance/g3-acceptance-runtime.py --milestone M2 --api-only --start-runtime，exit0，真实OIDC/API24检查PASS；API_ONLY gate1/1 PASS。编辑命名公理、三源逐字不变、PG修订重读、当前Jena SHACL assessment及428/409/400/403拒绝/修订hash不变均实测；两层sourceHead一致，owned launcher停止exit0。只证明首点，不代表UI/发布/完整M2。

slice_review非作者独立核对上述事实，PASS。第二UI_ONLY限定复审PASS：只M2/1gate/互斥、NOT_RUN清晰、full7gate+M1保留；9控制面green，独立M1-uiOnly和api+ui均exit2无资源。集成Web139/0skip与lint/typecheck/build日志已读。须冻结入口提交再真实UI实验。

当前point1同HeadCI 40523241211仍待实际最终结论；合同9bac1ff CI40519729967 canonical下载600秒超时已保留。不能将当前未知写成成功。point2及唯一V3/资源收尾待后续实际回执。
