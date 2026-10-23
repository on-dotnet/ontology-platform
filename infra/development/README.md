# 本地开发资源

唯一入口为 backend/src/AppHost/OntologyPlatform.AppHost.csproj；不维护第二份容易漂移的 Compose 资源模型。资源参数、健康端点、命名卷、启动顺序和重启验收见 [本地基础设施手册](../../docs/development/local-infrastructure.md)。

fuseki/Dockerfile 使用 Apache Jena 官方发行包自建开发镜像。此目录不存储密码、数据库文件、镜像产物、Docker 认证配置或企业生产数据。
