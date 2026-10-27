# 运行证据选择

当前有效执行必须按唯一`pipeline-<runId>/pipeline.json`选择；其中子环境再有`g3-m1-<prefix>/<runId>/acceptance.json`，记录准确sourceHead、身份、开始/结束和逐步PASS/FAIL/NOT_RUN。同一父/子目录只属于一次调用，下游只读该目录；存在旧PASS文件不是本轮证明。ModulesOnly为true的选择不能认证真实浏览器整栈。

本目录根部无pipeline前缀的文件是修复证据隔离前的历史状态，包含6a1c76c第三轮成功及随后02763a1补测失败后的残留；它们不能合并判为一次PASS。第三轮完整命令exit0、当时M1浏览器38/兼容reader/归属/标识/无损V2制品已独立固定在master/full-gate3-*及full-gate-attempt3.txt；随后429失败另存master/import-attempt1-*。原FAIL、残留及原时点事实保留，不覆盖成成功。

固定二进制仍在忽略的artifacts/g3-m1/fallback-reader-v4，本地126成员清单hash锚定写前构建源5df0765。每轮写前/写后分别把实际probe与制品hash保存在该轮目录；不把此reader称为旧G2应用降级认证。
