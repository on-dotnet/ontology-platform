# R0 非作者准入审查

Reviewer /root/recovery_reviewer，2026-11-01，实际模型/effort由宿主继承，未独立读取型号（NOT_VERIFIED）。R0_ADMISSION_PASS，仅R2受控取证，不批准容器运行。

独立验证输入ZIP CRC/Manifest/SHA256；基线三SHA；旧M1 V3 2778865 bytes / 070b2ab9ad1a3ad8c5e8de859f0b4018c7f5258eb9a3aea3f08ba6f0b4af371b / 759成员CRC正确；Before零容器、8旧卷、引擎及平台。

取证脚本SHA256 84d6274f9c8e1503cefd1b2c1d8b96131802f67da8fdc91d96529f629f96e4c0获审。16份Manifest固定摘要一致；32份ARM64 config/layer HEAD均200、长度吻合、无Location。固定输入/index/platform/config/layer身份链、单写锁、精确HTTPS主机、禁止隐式跳转/跨域认证头、持久预留3GiB和12GiB任务目录/宿主余量门禁通过。Reviewer另做5个纯内存拒绝检查（HTTP、未知host、userinfo、非443、预算耗尽）全部PASS；无联网写盘。

准予在 artifacts/g4-m1-recovery-001/forensics 逐镜像取证；GET新CDN主机暂停复审；Scout OFFLINE及任务cache、外层12GiB限额；无云扫描。本结论不代R3逐镜像许可。

精确共享路径准许：SecurityTests/packages.lock.json只补已有Connections项目依赖，host_continuity.py只追加恢复TaskId到preflight/monitor choices；不改电源策略。18项真实HTTP测试审查PASS_FOR_COMMIT，基线10PASS/8FAIL；限长修复静态无阻断，整合实跑待完成。

顶层官方许可独立只读查询HTTP200且无redirect：PostgreSQL官方许可页面8067 bytes SHA256 ae13310d123a7c5d1966c2030435512439510d9e3e35815853a3887188519d8d；Keycloak26.8.1 Apache-2.0 11358 bytes cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30；ASP.NET10.0.13 MIT1116 bytes cfc21f5e8bd655ae997eec916138b707b1d290b83272c02a95c9f821b8c87310；Node24.22.1主MIT及第三方集合157609 bytes 5888dbb9a1d2b18f2c3e6c5f6af1b39de658372b402a0577b002777f14c62ace。URL见输入blocked-witness sources。无已知禁止内部合成条款；不代完整镜像准入。

## CDN增量独立准入

Reviewer核实首个PG config GET的官方registry 307指向production.cloudfront.docker.com；执行器请求前拒绝，reserved17,396,932、received19,165，未读层。准许只追加此host，复用原budget不退预留。官方依据 https://docs.docker.com/docker-hub/release-notes/ （2026-05-20）及 https://docs.docker.com/desktop/enterprise/allow-list/ 。不向CDN转发Registry认证头，其他host仍停止。

Quay增量：Reviewer核对quay.io config实际HTTP302（Master消息曾误写307，本记录纠正）指向cdn01.quay.io，reserved342,290,545/received161,160,812，未读Keycloak层。Red Hat官方网络文档明确此镜像CDN，准许只追加HTTPS443精确cdn01.quay.io；同预算和认证隔离保持。来源 https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/plan-assembly_network_ports_protocols 及 https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/observability/installation_configuration/configuring-firewall 。

## Keycloak定向吞吐修正

层sha256:88202ac232a9ad53c5b04e32b6f3f6b4498772f8d069fbbde1d007f8dd31d981（173795289 bytes）原180秒实际读123731968 bytes后RESPONSE_TIME_BUDGET。已保存小层复用，原预留不退；原账本该request的STARTED保留历史原值，命令exit1见image-1-download-retry1.txt。1MiB/20秒短Range复现实际206、8.1715秒成功；Content-Range通过脚本当时断言但未保存原头，Reviewer不声称独立核实该头。非作者准许仅此层一次360秒重试，socket20秒和其余请求180秒不变；脚本持久keycloakExtendedAttempted拒绝重复昂贵失败。

MCR增量：Reviewer独立核对mcr.microsoft.com config GET实际307指向westus.data.mcr.microsoft.com，执行器在请求新域前拒绝，失败预留保持。Microsoft官方 https://learn.microsoft.com/en-us/azure/iot-edge/production-checklist 说明data.mcr.microsoft.com内容交付端点；仅准许HTTPS443准确westus.data.mcr.microsoft.com，不加通配。跨域不转发Authorization，仍须ASP.NET R3。

## ASP.NET定向吞吐修正

Reviewer核对sha256:59a63478dc4bc439321221551264a8824b65f489044e0ed81b8005da691126de，34455908bytes，原180秒读取23068672bytes，短Range206/1048576bytes/5.86142125秒及已留Content-Range正确。仅准此层一次360秒、持久aspnetExtendedAttempted；其余180/socket20和原失败预算保持。再次失败停止。

## 精确第三方NOTICE

附件已指定Keycloak26.8.1许可URL的GitHub302必要跳转release-assets.githubusercontent.com经非作者批准，仅该URL/HTTPS443/≤8MiB/原长度与SHA，计同账本，不扩registry白名单、不跟随HTML链接。官方分发依据 https://docs.github.com/en/actions/reference/runners/github-hosted-runners 。实际取得7523238bytes、SHA25614c17647c43f27315d148812a0be6b97b3cc9585463588ebbe67f7282cfe661d，完全匹配历史绑定；不自动构成R3通过。
