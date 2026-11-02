# 最小修复与输入绑定

R09仅增加Test-FrozenJsonlEvidence，准确路径不符合原始SHA或严格76行对象结构即json FAIL，不能回退普通JSON。其它JSON保持原行为，格式/秘密扫描继续。原G3-M4函数及五项断言逐字保留。
R10仅本机已登记PyYAML6.0.3副本：26文件逐SHA、无软硬链接、文件444/目录555、禁字节码。原44文件的内容/大小/权限/mtime/inode/uid均前后核验，不把文件读取atime当作写入。

真实局部测试Frozen新增64断言与旧5项PASS；StructuredFiles4项PASS；静态verify PASS。独立Reviewer初审无P0/P1；最终Review在稳定TestedCommit完整SelfTest之后另行执行。测试中预期json/结构解析失败是防护断言，不计为产品故障。

任务宿主适配器和其测试按已批准计划从只读POSTREVIEW对象借鉴，改为本任务精确身份；未合入其其它研究文档或产品提交。run-command只无损封装输出并记录真实退出与schema2计时，超时精确终止自身进程组。所有行为工具均额外记录SHA，最终Head必须与TestedCommit逐字相等，不借docs/evidence可复用说明规则放宽。

原Next-Task下载在首次执行时缺失，后由用户恢复，原字节及SHA已补存next-task-input-restored.json；最初观察保留。最终依据两份附件、已确认计划及明确用户执行授权。
