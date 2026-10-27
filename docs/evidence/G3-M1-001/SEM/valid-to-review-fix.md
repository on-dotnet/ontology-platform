# G2可选来源终点元数据兼容

依据：g2-thin-slice-contracts.md:74明确EvidenceRef.validToUtc?；PublishedGraph.cs:128–135读取可选validToUtc并验证时间格式/顺序。它是已有来源元数据，不是新增OWL-Time或M4时间模板。

真实PG/Jena/RustFS红灯：同一源码先以明确V1 Legacy策略真实部署/回验成功，新M1 Validate却Conforms=false；新增两例中validToUtc正例失败，相似未知validUntilUtc负例通过。仅metadata白名单增加validToUtc一项后，Publishing全套55/55通过、0跳过，包含validToUtc真实异人批准/激活V2及未知validUntilUtc仍422 assessment_not_eligible。OWL-Time仍按既有矩阵阻断，未扩新词汇。
