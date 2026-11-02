# 新G3镜像独立许可审查

Reviewer /root/final_gates_reviewer，非作者，只读原导出/原层及官方固定版本资料。两项均AMBER-A1/LICENSE_PARTIAL，不是GREEN。人类已逐项接受，仅内部合成非分发测试；不构成商业发布许可结论。

RustFS 1.0.3：官方index 9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b、ARM64 manifest a3951370f879374cb89cca3b495e05badab38807cc4cd609c54a35f93f6ccd64、config42fa39ec98fa40d8b80fa15322487f923e5555291dfb242f7df014996c0eee84，13blob独立SHA通过。45APK，唯一scanner空字段tzdata在原APK数据库为Public-Domain；镜像无许可正文，静态Rust crates/内嵌前端等未完整映射。官方精确revision顶层Apache2：https://raw.githubusercontent.com/rustfs/rustfs/331fb896285a7686f927baf8d9d4dc2d3d3a10a9/LICENSE 。标签拼接title仅辅助身份，不是签名。

canonical Fuseki manifest715703f0cdb98680f3b71ebbfcdea126ec1ddc3f483f4341afde2cc63b1a817c，12blob及196候选原字节逐项独立SHA通过。196含4个class二进制误入候选，正文应计192非class记录；一个Fuseki fat jar加一个JDK jrt-fs.jar。292扫描记录中158空许可字段（73deb/84Maven/1JDK），不少可由原版权和发行NOTICE解释，尚不完整。精确Jena6.2.0 Apache2：https://raw.githubusercontent.com/apache/jena/jena-6.2.0/LICENSE ；Temurin原NOTICE GPL2+Classpath及官方说明 https://adoptium.net/docs/faq/ 。shaded Java/前端/native与分发义务不完整。

两镜像未见禁止当前内部未修改非分发实验的已知实质冲突；CVE/签名/完整构建来源仍NOT_VERIFIED。RustFS Scout重建摘要f8cb不是官方manifest，不用于运行身份。原导出/扫描/原候选报告保留，可据准确Git索引恢复；报告不伪称完整SBOM。
