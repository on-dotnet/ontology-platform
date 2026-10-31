# 六Provider、模型网关及安全凭据设计

本轮交付可执行的离线配置/路由/预算/脱敏合同实验，未实现网络适配器或密钥输入程序。provider-catalog.json六实例全部disabled、外联policy未批准、模型UNSELECTED、capability/authentication UNKNOWN，真实请求/费用预算0。synthetic-price-v1只用于内存负例，不是市场价格。

## 配置分层与能力探测

Provider记录类型/region/base URL/protocol/SecretRef/egress policy/version；Deployment另记精确model、registry snapshot、context limit及能力。TaskProfile关联业务任务、scope、deployment、fallback和成本/外联策略。普通用户只选知识集及目标；管理员高级配置才修改模型，不把技术细节强加上传用户。任务级覆盖只能收紧组织策略，不能扩大厂区数据授权。

| Provider | 登记示例及官方证据 | 当前限制 |
| --- | --- | --- |
| OpenAI | https://api.openai.com/v1，Responses优先；[认证](https://developers.openai.com/api/reference/overview)、[结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs) | schema、拒绝、截断按精确model探测，不由JSON mode推断 |
| DeepSeek | https://api.deepseek.com；[官方接口](https://api-docs.deepseek.com/) | compatible不等于所有OpenAI能力；thinking/tools独立 |
| Qwen | 示例保留旧北京dashscope入口，disabled；[地区与工作区端点迁移](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope) | 新workspace域名与key地域必须匹配；官方页面北京示例存在地域文字不一致，以项目实际工作区核验后精确登记，禁止通配 |
| GLM | https://open.bigmodel.cn/api/paas/v4；[官方API](https://docs.bigmodel.cn/api-reference) | JSON Schema、视觉、推理、工具逐项实测 |
| Kimi | 示例CN https://api.moonshot.cn/v1；[国际兼容文档](https://platform.kimi.ai/docs/guide/migrating-from-openai-to-kimi)使用api.moonshot.ai | CN旧文档抓取timeout；CN地区端点本轮NOT_VERIFIED，不能自动改到国际出口 |
| Ollama | http://ollama:11434为Compose服务地址；[本地API](https://docs.ollama.com/api/introduction) | adapter须追加/api；仅显式本地授权，禁止切到云模型；宿主地址另登记 |

接口复用既有Microsoft.Extensions.AI 10.11.0等抽象的方向保持；Gateway是后端模块，管理策略、预算、Secret resolver、adapter和probe，不另造与现有MAF冲突的产品框架。本轮未改任何.cs或公共依赖。Python实验不是生产.NET实现。

认证成功只表明一次凭据/端点检查成功，不证明jsonSchema/vision/embedding/tools/streaming/reasoning。每项Probe绑定provider/deployment/model/schemaHash/sampleVersion/probeVersion；模型/输入/schema改变即失效。未来探测含有效、拒绝、截断、坏JSON、额外属性、类型不符、工具注入和网络超时，服务端校验失败不形成Claim。Provider异常映射固定分类，不透传body。

## 无回显输入、存储、SecretRef

后续获批时独立CLI在真实TTY用无回显输入，非TTY拒绝；不接受命令位置参数、聊天、Prompt、shell历史或自动抓取Codex登录token。现有ChatGPT/Codex登录授权不作为模型API凭据。用户可取消，不保存部分输入。

macOS用用户Keychain，Windows用Credential Manager/DPAPI用户边界，Linux按目标宿主批准的secret store；拒绝明文自动降级。SecretRef只存随机id/provider/tenant/version和受限挂载路径，不保存key后缀或hash。轮换创建新版本，旧引用明确撤销，已有job不得静默换scope。授权后的临时文件目录0700/文件0600或等价ACL，排除备份/日志/压缩包，写入原子且拒symlink；只读挂api，最后准确unlink并验证不存在。SSD物理擦除不能靠unlink宣称；以系统加密与生命周期管理降低风险。

当前不调用Keychain/DPAPI/getpass，不索取key。离线测试在内存生成无效MOCK值，捕获stdout/stderr/异常/JSON，验证日志仅固定status。未来UI只显示已配置/未配置/已撤销和安全错误码，认证与能力两列独立；API DTO不返回Secret值。审计ID需服务端生成并allowlist，不能因为字符串格式合法就把任意用户字段写入遥测。

## 外联、费用与失败

数据分类SYNTHETIC/PUBLIC/INTERNAL/CONFIDENTIAL由权威策略判定；原文、图片、embedding输入与失败回退均算外传。每个fallback目标重新授权scope/region/classification/egress/capability，并预留自身预算，不因首选失败跨厂商。静态URL检查只是第一层；真实实现还需解析IP、拒私网/metadata、TLS和代理出口控制，禁止重定向和环境代理绕过。

CostPolicy包含请求数、输入/输出token、USD费用、wall time、重试和并发上限。未知价格/用量拒绝；调用前按最大输出预留，失败是否计费不明不退款。金额输入是有界十进制字符串，实验转Fraction作精确有理数运算，避免Decimal默认精度向下舍入超预算；账本只模拟单进程顺序，分布式幂等和持久一致性待实现。请求id重复拒绝；重试消耗新请求预算。真实额度仍为0；后续建议上限最多50请求/5USD只是申请草案，需精确model/价格时间戳和人类批准，未批准不执行。

失败状态至少认证、余额、429、TLS、网络、模型不存在、schema不支持、拒绝、截断、预算、政策拒绝；每种仅固定枚举。认证失败不自动换key、余额不足不自动换供应商、不可用不打印response body。运行期和Docker Secret权限测试均NOT_RUN。
