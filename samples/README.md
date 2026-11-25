# 样例

| 目录 | 内容 | 用途 |
|---|---|---|
| [steel/](steel) | 钢铁冶金案例：本体（炉次、浇次、板坯、轧制事件、钢卷）、约束、术语、单位、合成数据（含一份不合规数据） | 案例演示、AI 识别评测、校验测试 |
| [pharma/](pharma) | 药品批生产（片剂）案例包：6 份资料（PDF、Word、Excel）与期望答案 | AI 识别评测的留出集，只用来测量 |
| [owl-features/](owl-features) | 21 个 OWL 特性样例，从 IRI、类、属性到限制、基数、属性链、导入、身份、时间与复杂公理 | 导入导出往返测试（M2：全部导入再导出不丢内容） |

数据均为合成数据，不含任何企业真实信息。

## 识别评测的案例包

一个案例包是 `samples/<案例>/` 下的 `docs/`（资料）与 `eval/expected.toml`（期望答案），由 `./dev.ps1 eval <案例>` 运行和打分，答案格式见[开发手册](../docs/development.md)"识别评测"一节。

规则：

1. **答案先写**。`expected.toml` 在任何一次模型运行之前写好并提交，git 历史里答案的提交早于第一次评测。写答案的人只读资料和收录标准（可参照 `steel/eval/expected.toml` 开头的说明），不看识别代码、提示词和任何模型输出。
2. **跑过模型之后不按模型输出改答案**。确实写错的条目另开 PR，逐条写明理由和原文依据。
3. **留出集只用来测量**。`pharma` 不许用来调规则或提示词：不对着它的分数、未命中项或模型输出改 `extraction.py`、`prompts.py`、`pipeline.py`。调规则用 `steel` 或新建一个开发用的案例包。
4. `steel` 的答案在 #7 时按模型输出补过，它的分数不算留出集分数。

**真实资料不入库**。脱敏后的真实资料不放进 `samples/`，放在 `.verification/private-docs/<名称>/`（已被 Git 忽略），结构同上，答案可以后补；用 `./dev.ps1 eval .verification/private-docs/<名称>` 评测，结果和录制也只写在 `.verification/` 下。评测时资料内容会发给配置的模型服务，资料要先脱敏。

## pharma 的资料怎么重新生成

`pharma/docs/` 下的 PDF、Word、Excel 由 `pharma/build/build.py` 从 `pharma/build/src/` 的源文件生成，生成工具（reportlab、python-docx、openpyxl 与文泉驿微米黑字体）只装在临时容器里，不进项目依赖：

```powershell
./samples/pharma/build/generate.ps1
```

脚本在 Docker 主机上起一个 `op-tmp-` 开头的临时容器，用完即删；build/ 目录经标准输入传入，生成的文件经标准输出取回。改了资料内容属于改留出集，答案要按规则 1、2 同步处理，旧的评测录制也随之失效。
