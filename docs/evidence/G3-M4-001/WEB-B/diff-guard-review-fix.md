# 独立Review P2：四源回复结构守卫

原缺陷由非作者Reviewer真实构造：普通对象sourceSlots继承Object.prototype，四个来源名__proto__/constructor/toString/hasOwnProperty配合缺字段和空hash可通过原谓词，随后图展示访问崩溃。Owner确认并保留原f90提交，不改历史。

修复：Map精确四个source槽位，必需自有字段逐项检查，From/To固定版本和scope、五项64hex散列、DRAFT-null/RELEASE-64hex manifest、Graph状态/统计、typed增删基本结构和缺席/原文变化均在渲染前失败关闭。hash另有精确length=64，避免正则$接受尾随LF。

窄回归17/17、0fail/0skip，覆盖原prototype样例、缺Graph/原文/hash/delta字段、manifest种类和格式、畸形Graph/typed triple，保留原14项字节/版本/范围边界。typecheck/lint exit0；后置仅加hash精确长度窄改，最终B回归再覆盖该负例。真实Diff浏览器由Master执行，未冒称本次已验证。独立复审待真实结果。
