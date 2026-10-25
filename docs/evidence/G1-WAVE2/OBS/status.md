# G1-OBS-001 验证状态

状态：EXECUTING / PARTIAL。实现基线：87eb51a77bffe7468164a0e418bbbd2e101d95bc。Owner 仅写冻结 OBS owned_paths；Master 唯一注册 AppHost。

- 官方精确稳定发布、镜像 index/ARM64 digest、许可证：核验中。
- 完整镜像 CVE/SBOM 扫描与签名验真：NOT_VERIFIED，不能等同官方标签安全。
- 真实 API→Alloy→Loki/Tempo/Prometheus、中文 Grafana 截图、告警触发恢复、重启持久化：NOT_RUN，等待统一 AppHost。
- 本地存储；RustFS/S3兼容、生产HA/保留策略、Windows/Intel：NOT_RUN。
- 独立Review/CI同Head：NOT_VERIFIED；本分支不自行合main、不另制ZIP。
