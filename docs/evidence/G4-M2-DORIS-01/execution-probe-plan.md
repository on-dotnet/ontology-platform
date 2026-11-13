# 最短服务探针方案（待非作者执行准入）

本方案只实现已批准A–F第6.2步的真实可行性见证，尚未执行。当前资源前提已读回：Engine至少15GiB、map_count2000000、无swap、nofile65536；启动前再次核实，用户能源策略确认沿用并重新preflight。不改变VM设置，不跳过BE检查，不下载镜像。

## 精确边界

- 两个固定ARM64 digest，采用`infra/doris/compose.yaml`及`compose.test.yaml`；独立project/run标签，内部网络，无Docker socket/宿主系统挂载，无privileged，无capability；不启动PG/OIDC/API/Web。
- FE4GiB、BE6GiB，memory-swap=memory，FE堆2GiB、BE堆512MiB/native mem_limit3G。串行宿主探针RSS合计上限4GiB。线程/非堆与最终cgroup生效情况须inspect及运行观测，示例值不是性能承诺。
- 仅发布FE `127.0.0.1:19030→9030`，先绑定冲突检查；内部BE `be:9050`，不对宿主发布BE/RPC/HTTP。宿主客户端固定`localhost:19030`，VerifyFull+任务CA、Pooling=false，不修改hosts/全局信任。
- 私有runtime目录0700、密钥/管理员及reader口令文件0600；任务CA和服务证书，DNS SAN localhost。FE使用外置PKCS12，初始root口令为随机口令的两阶段SHA1；不得将默认空口令实例发布到宿主。配置/证书生成及检查不得输出秘密，不归档私钥或口令/hash。
- 镜像中已核验的`start_fe.sh/start_be.sh --console`负责启动，保留其JDK和系统检查。目录、网络、卷与容器创建即记准确ID；不依赖全局prune。

## 有界顺序

1. 静态渲染真实私有路径配置（仅私有原件），拒绝REPLACE标记、缺失文件、镜像/网络/内存/发布端口漂移；检查累计磁盘25GiB和过程产物1GiB。
2. 明确非作者服务执行准入后创建并启动FE，再BE；整个就绪期限240秒，每次短探针≤10秒，进程退出/OOM/最终超时立即停止昂贵链。不以TCP health或Running代替成功。
3. 宿主MySqlConnector2.6.2通过原生FE MySQL TLS认证管理员，注册BE；检查FE/BE存活，创建固定internal.fixture的单副本、单桶、极小元数据表；所有SQL来自固定夹具，不接受用户SQL。
4. 建独立fixture_reader及固定fixture库SELECT权限，直接TLS读取版本/连接ID/SHOW GRANTS/表和字段元数据；源管理员只用于夹具和旁路观测，绝不进入应用凭据。
5. 通过错误CA/错误SAN拒绝证明VerifyFull确实生效；连接与读取共享10秒总deadline。错误证书与过期证书、权限继承/跨库反例完整集放入后续产品验收，最短探针不得冒充全量完成。
6. 合成耗时查询采用reader身份，明确源连接ID，发起取消并由管理员观测该ID的查询消失/终止；辅助取消连接仍同目标同TLS同reader身份，单独有界清理。若取消或TLS不可用，停止适配器实现长链并短定位，不授予reader管理员权限。
7. 记录退出码、实际耗时、峰值、有效参数、源端身份与私有日志脱敏摘要。失败保留原件；只按准确ID回收本任务资源并核验后验。活跃数据/缓存保留理由明确，不生成中间ZIP。

NuGet探针仅使用已验证net10资产与已有SDK/框架；离线build禁止网络，不隐式安装或改锁。本探针不是产品完整凭据生命周期、CI、生产、备份恢复或性能验收。任何适用重大风险未处置均先停运行；SBOM/签名可得性/全量CVE未知依DORIS-LOCAL-01分别记录，不能伪写安全PASS。
