# 三项易失资源保全与恢复卡

Owner 为 G4-DORIS-MAPPING-QUERY-001／implementation-01。三个 local tmpfs 卷的持久副本与独立恢复尚未确认，均 KEEP_RUNNING。准确标签、资源上限及三个持久容器见[实时读取原件](originals/resource-start.json)。

- **keycloak-test**　容器 `3f1502f453da342d8cd57ab6514852d1fa06007baad709156abb7da0e5e2647f`，镜像 `sha256:e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4`，卷 `ontology-g4-doris-mapping-query-001_keycloak-data` 挂载于 `/opt/keycloak/data`。H2 身份库、realm、用户和主体 ID，依赖现有客户端与签名材料。隔离副本须验证原主体 OIDC 登录及密钥版本。
- **fuseki**　容器 `d3f2a4b9dd9d06bf3141e35c80b4c96246b47cc81092762f88171bf57dff5e04`，镜像 `sha256:715703f0cdb98680f3b71ebbfcdea126ec1ddc3f483f4341afde2cc63b1a817c`，卷 `ontology-g4-doris-mapping-query-001_fuseki-data` 挂载于 `/fuseki`。持久发布图与 TDB2 数据集。隔离副本须全库读取，核验已发布图 IRI、三元组及 SHACL。
- **rustfs**　容器 `57ef8d99c6eb37eb4681f9ae707537de93b556218394ad54c8703b2f2b2f5ce9`，镜像 `sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b`，卷 `ontology-g4-doris-mapping-query-001_rustfs-data` 挂载于 `/data`。已发布制品对象、版本与原字节。隔离副本须用受限凭据按数据库槽位回读取散列、长度与版本。

释放条件须同时满足：先核对准确 ID、卷与引用，封闭新投递并有界排空，核定存储和密钥的独立保存位置，取得应用一致的私有副本，原挂载持续持有；仅在另批明确授权后演练隔离同身份恢复并核对以上服务依赖、合成主体以及原发布字节。由非作者核验保全与恢复清单后集中裁决。任何缺项继续原挂载。旧 M4/M5 另属其原任务。
