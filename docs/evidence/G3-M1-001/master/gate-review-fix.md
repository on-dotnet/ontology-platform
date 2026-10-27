# 公共门禁修复第一轮

V2 reader仅在schemaVersion2核完整4hash/可选词汇及BundleHash精确拼接关系，V1不升级。独立固定空源散列夹具，新增真实RED1/1→完整23PASS/1缺制品NOT_RUN；真实制品专门reader1/1零skip。Schema同步V2格式，真实运行OpenAPI仍需重新导出。

写入前对保留reader全部126文件（含Contracts.dll）冻结path/size/SHA，前后成员/字节严格比较，拒绝symlink。父验收器固定freeze文件自身SHA并传至后验过程，缺/变更失败。新增真实文件替换/成员注入缺失/链接负例RED3→GREEN3。不能把只hash入口DLL当全部parser身份。首次正式栈前从已提交合同源码重新构建候选reader；原各代二进制保留，不覆盖。
