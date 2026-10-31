# PREP Parser / SourceMap 合同 v1

仅标准库合成文本实验，不是正式产品 DTO、本体权威或 Docling 适配器。Master 单写；字段以本文冻结，Python 实现允许 snake_case，JSON 必须有明确版本。

## 不变量与结构

DocumentVersion：document_id、version_id、version（正整数）、scope（非空组织/厂区身份）、format（TXT/MD/CSV）、source_sha256、size_bytes、encoding=UTF-8；原件 raw bytes 不变，身份含 scope+document_id+version+hash，不能仅按内容跨 scope 复用。任何构造/反序列化后校验绑定真实 bytes；bool 不是整数。时间只保留明确输入，不能把文件 mtime 当业务时间。
ParseArtifact：artifact_id、document_version_id、parser_name、parser_version、config_digest、source_document_hash、ir_schema_version、source_map_hash；配置采用排序紧凑 UTF-8 JSON，拒 NaN，记录精确解析器版本，变更配置/源/版本/范围使身份变化。
DocumentIR：document_version、parse_artifact、text、blocks、cells、source_map、quality_signals、mode、graph_artifact=null。DOCUMENT_ONLY 永远无 RDF 图；所有模式本批仅 IR，无 Claim 发布。
SourceAnchor：document_version_id、source_document_hash、parse_artifact_id、precision EXACT|BLOCK|PAGE|UNKNOWN、segments[]、text_hash，page/block/cell 可选。本批 TXT/MD/CSV 不声明页/bbox；UNKNOWN 不得给精确坐标，BLOCK 仅有实际块引用，无高亮资格；PAGE 本批拒绝（无页证据）。EXACT 至少一非空 segment，每段含原件 byte_start/end 与 codepoint_start/end 及 IR start/end。半开区间，非负、不逆序、不越界、字节须 UTF-8 边界、两套坐标回读一致，不能用 UTF-16/字素索引替代 codepoint。

## 映射算法边界

原件严格 UTF-8 decode，不使用 replacement/ignore。原始 codepoint 坐标包含 U+FEFF BOM（若存在），byte offset 包含 EF BB BF。IR 可移除开头 BOM，CRLF/CR 统一 LF；不做 NFC/NFKC、trim、大小写变更，组合字符/emoji 保持各 codepoint。SourceMap 每个 IR codepoint 映射一个原件 codepoint 半开 span；CRLF 的一个 LF 映射两个源 codepoints/bytes。映射顺序、范围、精确转换内容以及原件 hash 必须重验，不能信任用户提供 map。
多段证据明确保持有序分段，不能把不连续证据伪装连续，重复文本通过指定 occurrence/range 消歧，默认重复匹配必须 AMBIGUOUS。Anchor 文本 hash 对明确拼接的各段 IR 文本计算；原字节及原文片段均可从 segments 回读。旧版本/同字节新 version_id/不同 scope/artifact/config 均不能沿用旧 Anchor。
CSV 使用确定性 RFC4180 子集：逗号、双引号、双引号转义、多行字段、空字段、行列/表头引用；公式内容只作字符串，不能执行。逻辑 cell 文本与 lexical 源段分离，去引号/双引号折叠须由 cell SourceMap 表示；无法证明精确映射应拒绝或 BLOCK，不能猜 offset。拒未闭合引号/引号后垃圾/列数不齐等明确坏 CSV；保留物理换行来源。

## 安全入口与预算

仅指定 fixture 根下的普通文件；拒绝绝对路径、..、反斜线/Windows drive、符号链接（含祖先）、目录、FIFO、URL。POSIX 使用 nofollow/openat/fstat 防竞态；平台无等价能力明确 BLOCKED/NOT_SUPPORTED，不用 resolve 后普通 open 伪装安全。权限拒绝用真实 chmod/读取或注入 OSError 并明确区分。读前检查与 max_bytes+1 有界读取，max_bytes 默认1MiB，max_codepoints 262144，max_segments 128，CSV cells 10000；超限拒绝不截断。所有异常仅固定安全 code，不含内容/路径/Secret。不发网络请求、不执行内容、不加载插件。

## 必须先写的负例与对应正例

坏 UTF-8/截断/孤立 surrogate；BOM/CRLF/CR/LF 混合；中文/emoji/ZWJ/组合 Unicode；重复内容+时间不当身份；空文件/空 span/越界/byte中间/篡改map/hash/config/artifact/scope；多段重叠/逆序；CSV 引号/逗号/多行/空/公式/坏列；路径穿越/祖先链接/文件链接/FIFO/过限/权限；版本变化和同 bytes 新版本；DOCUMENT_ONLY 图为空；9 seed/18已声明span全部回源并核 hash；Prompt Injection 仅文本。对缺功能真实失败留记录，再实现后全通过。

## 冻结附录 A：canonical 身份 v1

C(x)=json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")；H=小写 SHA256 hex。只接收合同字段，字符串不做Unicode规范化；字典键必须字符串，列表保持顺序，禁止float/nonfinite/重复JSON key。scope 固定 {organization_id:非空字符串, site_ids:非空去重ordinal排序字符串列表}。
version_id="dv-"+H(C({schema_version:1,document_id,version,scope,format,encoding:"UTF-8",source_sha256,size_bytes}))；version 必须 int且非bool且>=1；原件bytes不入JSON而以上hash绑定。不能任意指定 version_id；反序列化必须重算；相同bytes的新version或scope产生新id。
config_digest=H(C(config))；config固定 {strip_bom:true,normalize_newlines:true,unicode_normalization:"NONE",csv_dialect:"RFC4180_SUBSET",max_bytes:1048576,max_codepoints:262144,max_segments:128,max_cells:10000}，所有预算可降低但必须正整数且不超过默认；未知字段拒绝。
source_map_hash=H(C({schema_version:1,document_version_id,source_document_hash,global_spans:[[source_cp_start,source_cp_end],...],cell_maps:[{row,column,spans:[[source_cp_start,source_cp_end],...]}...]}))。cell_maps按row,column排序，无cell时空数组。
artifact_id="pa-"+H(C({schema_version:1,document_version_id,source_document_hash,parser_name:"stdlib-synthetic",parser_version:"1.0.0",config_digest,source_map_hash,ir_schema_version:1}))。validate 从实际raw/config/text/maps重算全部身份，不能互相比对自报hash即通过。

## 冻结附录 B：CSV 坐标空间

DocumentIR.text 永远是全局规范化 lexical CSV（含逗号和引号）；cell.text 为去包围引号/折叠双引号后的逻辑字符串。cell row/column 从0起，row0为header；header_ref 为同column的row0 cell（header自身null）。SourceAnchor增加 text_space="DOCUMENT"|"CELL"；CELL必须有row/column，ir_start/end在该cell.text中，不允许混合空间；DOCUMENT不带cell。cell专属map直接映射原件cp，不通过含糊 find。多个segment在所选空间严格有序不重叠；空cell保留结构但不可创建非空EXACT span。
输入原件 h\r\n"a""b"\r\n：原cp 0=h,1=CR,2=LF,3=quote,4=a,5=quote,6=quote,7=b,8=quote,9=CR,10=LF。全局text=h\n"a""b"\n；cell(row1,col0).text=a"b，cell map=[[4,5],[5,7],[7,8]]；CELL [0,3) -> 原cp/byte [4,8)，text_hash=H(UTF8(a"b))；双quote的单个逻辑quote定位原[5,7)。引号装饰不属于cell内容，不伪造连续规范化全文坐标。带CRLF的quoted cell其LF同样映射两原cp。
