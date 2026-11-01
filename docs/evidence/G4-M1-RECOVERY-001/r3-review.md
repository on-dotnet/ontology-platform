# R3 非作者逐镜像风险审查

Reviewer: /root/recovery_reviewer，read-only quality_reviewer，独立于实现作者；模型身份 NOT_VERIFIED。范围仅本任务内部合成、非分发实验，不代表商业部署合规。CVE、签名、provenance 均 NOT_VERIFIED。

## PostgreSQL 18.6

结论 AMBER-A1 / LICENSE_PARTIAL。固定ARM64 `sha256:9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437`。Reviewer直接从原层复算168许可记录；205包中29未知字段包括25个有本地Debian许可的包和4个Go组件，官方精确版本来源补强见r0材料。SBOM SHA256 `34329b7a20eeee7d976e7d6eb1770e611a65e08aa81cec8e625fd24005fcfbac`，许可报告 `db4749d9a0e126fe0dea7bf382030c4e28c9cada993163fd2316cfd607dfa3f3`。

GCC exceptions、GnuTLS、MIT Kerberos、libxcrypt、libgcrypt/libksba、tzdata及gosu1.19 / moby sys user0.1.0 / golang sys0.1.0 / go1.24.6已逐项判断。Sleepycat/db5.3、SMAIL-GPL、BSD4/MS-PL义务留待G8；common-licenses存在AGPL文本本身不证明包使用该许可。未发现阻断本次内部未修改运行的实质冲突；不宣称完整分发合规。

## Keycloak 26.8.1

结论 AMBER-A1 / LICENSE_PARTIAL。固定ARM64 `sha256:e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4`。44 RPM、487物理JAR、443properties坐标、447POM记录、252Bundle-License、293许可文本引用、576JS、29内嵌native独立原层复算通过；1435文本原字节及1246去重SHA一致。手工SBOM `7ffe94f56cc98810b03fad9cd8feedccdde2006876050e91956a937afa1020ea`；companion `8080f7d3d479918f1c5f3fb51e85ce767018ea98c04a5709de9150940218a1d3`。Scout180秒失败及20秒短复现失败保留，手工状态 MANUAL_OFFLINE_PARTIAL。

精确发布NOTICE 7,523,238 bytes，SHA256 `14c17647c43f27315d148812a0be6b97b3cc9585463588ebbe67f7282cfe661d`，806依赖段含263个npm风格坐标，补强精确版本许可及正文。444/487 JAR可经坐标或版本文件名匹配，余43主要38自有Keycloak模块、3生成JAR、JRE jrt-fs及mssql版本表示差异（内嵌MIT）。185无内嵌许可JAR通过版本NOTICE、自有Apache2、生成物、JRE GPL2+Classpath和mssql MIT分别解释，未知未自动放行。

保留：NOTICE自称best-effort，部分Source URL指main/master；Graal nativeimage/word25.0.4.1标UPL但附总体GPL2+Classpath；Angus2.0.5标BSD3而正文EPL2+Classpath/EDL。保守观察条款均无禁止本次内部未修改非分发运行，未见收费或实质使用权冲突，因此A1。MySQL9.7 GPL2+Universal FOSS exception、Narayana7.3.4.Final及RPM GPL/LGPL/MPL保持对应义务。G8需协调标签/正文差异、shaded Angus/Narayana子模块、576编译JS对263声明、148外层/29内嵌native及JDK模块归属、完整NOTICE和源码分发义务。禁止宣称FULL/GREEN。

具体容器运行仍受R4配置审查约束。

## ASP.NET 10.0.13

AMBER-A1 / LICENSE_PARTIAL。platform `3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55`，6层92,392,505bytes独立SHA核对；runtime.version为10.0.13。Scout offline exit0 /3.031s，138记录、17未知；SBOM `02d52725a329000177c26f43b003a5c2dca30e4caa9bbc3b27963bca79c23707`，licenses `5556d37c699eebf5f512aa910dd6515ae38a9313c77afe750097f463dacf302a`。110原层许可文件复算，4链接仅索引。17未知逐组：base-files GPL2+；gcc四记录GNU版权和运行时例外；glibc三记录LGPL2.1+/GPL工具（发行版权文本2.23滞后当前2.39保留）；gnutls两记录LGPL/GPL；libxcrypt两记录LGPL/BSD；libgcrypt LGPL/GPL工具；libtasn1 LGPL；ubuntu-keyring公钥不受版权/支持GPL；两NuGet runtime由镜像MIT与77,436B ThirdPartyNotices补证。NOTICE历史ASP.NET Apache2与顶层MIT差异及ISO SGML限用途片段未发现本次内部运行实质冲突，G8需协调。无额外源请求。

## Node 24.22.1

AMBER-A1 / LICENSE_PARTIAL。platform `a52166d89cfcc66ea62d10535ca712d161cece5d77ff4cfa758866b6b75ccb3f`，5层83,027,875bytes独立SHA通过。Scout offline exit0 /4.043s，259记录（112deb+146npm+1github）；SBOM `406eaf3264aef3220f99d74720bc8955f7461d01ddba8fa3a6d139f987de89b8`，licenses `c7dfdce4ef842a526a846250c8b9d2fbcc2f2a69eaeb054e90e53856d47ec893`。216原许可文件复算、3链接索引，共1,731,715text bytes；Node原LICENSE与官方精确v24.22.1源相同。9未知：debian-keyring公钥/支持GPL，gcc四记录GNU+runtime exception，libxcrypt两记录LGPL/BSD，tzdata public-domain，qrcode-terminal0.12.0旧licenses数组Apache2及原LICENSE含Apache2+vendorMIT/商标通知。已知Sleepycat/BSD广告/GPL/LGPL/MS-PL义务与最终文件系统/应用依赖完整映射保留G8。不授权npm install、新依赖或域名。
