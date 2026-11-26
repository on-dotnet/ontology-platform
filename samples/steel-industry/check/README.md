# 运行钢铁案例自检

在仓库根目录用 PowerShell 7 运行 `./samples/steel-industry/check/check.ps1`。需要能访问 Docker 上下文 `linux013-rootless`。
默认从阿里云安装锁定版本的依赖。使用默认 PyPI 源时，先执行 `$env:OP_MIRROR = 'off'`。
退出码为 0 表示全部通过。失败时，按输出中的文件、约束或查询编号定位。
