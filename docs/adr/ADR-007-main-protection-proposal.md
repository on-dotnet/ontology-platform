# ADR-007 · main保护规则建议

状态：PROPOSED，仅建议不实施仓库规则修改。2026-10-25 Wave2要求重新只读查询GitHub分支/规则事实，具体观察归档在本轮证据。建议为main要求同Head工程/安全/前端CI、至少一位非实现者PR审查、禁止强推/非快进和删除，紧急旁路需人类审计。当前无修改仓库规则授权，Master不调用写API；启用前继续依靠独立Reviewer、真实分支CI、Master唯一集成与普通push。GitHub计费/配额未知时不启新收费Runner。
