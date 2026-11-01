# R0 非作者准入审查

Reviewer /root/recovery_reviewer，2026-11-01，实际模型/effort由宿主继承，未独立读取型号（NOT_VERIFIED）。R0_ADMISSION_PASS，仅R2受控取证，不批准容器运行。

独立验证输入ZIP CRC/Manifest/SHA256；基线三SHA；旧M1 V3 2778865 bytes / 070b2ab9ad1a3ad8c5e8de859f0b4018c7f5258eb9a3aea3f08ba6f0b4af371b / 759成员CRC正确；Before零容器、8旧卷、引擎及平台。

取证脚本SHA256 84d6274f9c8e1503cefd1b2c1d8b96131802f67da8fdc91d96529f629f96e4c0获审。16份Manifest固定摘要一致；32份ARM64 config/layer HEAD均200、长度吻合、无Location。固定输入/index/platform/config/layer身份链、单写锁、精确HTTPS主机、禁止隐式跳转/跨域认证头、持久预留3GiB和12GiB任务目录/宿主余量门禁通过。Reviewer另做5个纯内存拒绝检查（HTTP、未知host、userinfo、非443、预算耗尽）全部PASS；无联网写盘。

准予在 artifacts/g4-m1-recovery-001/forensics 逐镜像取证；GET新CDN主机暂停复审；Scout OFFLINE及任务cache、外层12GiB限额；无云扫描。本结论不代R3逐镜像许可。

精确共享路径准许：SecurityTests/packages.lock.json只补已有Connections项目依赖，host_continuity.py只追加恢复TaskId到preflight/monitor choices；不改电源策略。18项真实HTTP测试审查PASS_FOR_COMMIT，基线10PASS/8FAIL；限长修复静态无阻断，整合实跑待完成。

顶层官方许可独立只读查询HTTP200且无redirect：PostgreSQL官方许可页面8067 bytes SHA256 ae13310d123a7c5d1966c2030435512439510d9e3e35815853a3887188519d8d；Keycloak26.8.1 Apache-2.0 11358 bytes cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30；ASP.NET10.0.13 MIT1116 bytes cfc21f5e8bd655ae997eec916138b707b1d290b83272c02a95c9f821b8c87310；Node24.22.1主MIT及第三方集合157609 bytes 5888dbb9a1d2b18f2c3e6c5f6af1b39de658372b402a0577b002777f14c62ace。URL见输入blocked-witness sources。无已知禁止内部合成条款；不代完整镜像准入。

## CDN增量独立准入

Reviewer核实首个PG config GET的官方registry 307指向production.cloudfront.docker.com；执行器请求前拒绝，reserved17,396,932、received19,165，未读层。准许只追加此host，复用原budget不退预留。官方依据 https://docs.docker.com/docker-hub/release-notes/ （2026-05-20）及 https://docs.docker.com/desktop/enterprise/allow-list/ 。不向CDN转发Registry认证头，其他host仍停止。
