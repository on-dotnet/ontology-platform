# FE依赖补充

官方registry.npmjs.org实测：Next16.4.3支持React19；eslint-config-next16.4.3声明eslint>=9，实际typescript-eslint8.72.0拒绝TS7.0.2。TypeScript修订待Master登记。

Master确认编译类型包精确加入：@types/react19.3.0、@types/react-dom19.3.0、@types/node24.19.2，官方npm/DefinitelyTyped，MIT。无额外组件或图标库。

安装默认禁止unrs-resolver1.12.2脚本，未执行；完整传递依赖许可/漏洞与签名完整性NOT_VERIFIED。Playwright无HAR/trace/视频，最终截图仅非敏感UI。
