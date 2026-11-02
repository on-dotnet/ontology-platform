# 独立Reviewer定向补证要求
首轮R04 33断言PASS保留，但版本2仅注释变化不能排除Jena混版，审计仅非空不足。最终需运行内变更dataTurtle及reified assertion，实测v1→故障v1→v2→回滚v1值与hash/graph/objectKey绑定；503必须artifact_store_timeout，active ID/hash/revision不变，成功revision连续及精确审计Trace关联。
C08补B新分支：public空成功、关系/函数/独立类型各非空拒绝、public缺失拒绝、撤销有效USAGE拒绝，恢复空及原权限后成功。每状态A成功，对象与字段完整目录A/B相等。历史103证据和402绑定独立复算相符，其余47按产品三文件影响分类复用，不机械全量跑。
