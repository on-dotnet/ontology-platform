# M5窄屏截图复核与真实CSS短回归

状态：PASS；Master真实OIDC重拍202fd26ff8bb4362914bb81a98623fdc已exit0/50检查，三张新PNG已重开；非作者独立layout3/0并查看窄屏通过。视觉调查Base=`82cb56963eca98e0d26d6b68a89cd08221587805`；独立树40e2，分支codex/g3-m5-web-visual。只新增局部浏览器测试和本文；未修改任何生产CSS/Workspace/Design Tokens，也未启动容器或运行完整build/业务验收。

## 根因与边界

Master提供390x844截图显示左侧残留约66px导航并盖住标题。实际CSS在850断点使用fixed sidebar、translateX(-100%)及200ms transition；桌面先稳定再缩窄的逐帧读取观测sidebar.right由230降至0，heading.left始终16。现有稳定布局无需改动，不能为消除瞬态截图改变产品动画。

inert会让elementFromPoint跳过导航，但不会阻止它被绘制；故单纯hit-test和document.scrollWidth<=innerWidth均不能证明没有遮挡。新负例仅在隔离夹具注入部分可见导航，实测文档无溢出仍有真实边界重叠。Master应在真实页面等closed sidebar.right<=0、主标题/内容/面板rect均在viewport内，再用animations:'disabled'采集稳定截图；最终真实页面结果另绑定。

## 实测：现有生产CSS，正常enabled按钮

测试直接加载仓库globals.css、ontology/workspace.css和expression-tree.css，使用既有Edge/Playwright；无复制硬编码token。两种主题在桌面缩390、过渡自然完成后均为：sidebar.right=0；heading/panel范围16..374；main范围0..390；无横向文档溢出。抽屉正向打开与关闭、键盘从active tab到refresh均通过。真实React的ARIA/inert同步及OIDC不由此静态夹具代验。

|主题|按钮|实际前景RGB|实际背景RGB|对比度|状态|
|---|---|---|---|---|---|
|dark|高阶表达式active|232,237,246|36,52,91|10.4093:1|enabled，opacity1|
|dark|刷新高阶表达式|232,237,246|19,27,41|14.6945:1|enabled，opacity1|
|light|高阶表达式active|30,42,65|237,240,255|12.6538:1|enabled，opacity1|
|light|刷新高阶表达式|30,42,65|255,255,255|14.3568:1|enabled，opacity1|

上述两种正常操作按钮均达到普通文字4.5:1；没有据disabled控件截图下结论，没有修改配色。主题background本身有150ms过渡，测试在真实动画finished后计算，不拿过渡中间帧当稳定配色。

## 真实检查与复跑

新增`apps/web/tests/ui/mobile-navigation.spec.ts`三例：dark稳定布局/交互/对比、light同项、无溢出但inert导航遮挡负例。首次实际3 PASS/0 FAIL/0 skipped，1 worker，3.0s。首次执行采用本任务ignored临时无webServer配置；随后Master批准永久最小入口`apps/web/playwright.layout.config.ts`，该入口最终实跑3 PASS/0 FAIL/0 skipped、2.9s，未使用Next server或业务服务。ESLint与typecheck最终均exit0。首次typecheck发现fixture样式handle推断为Node、无remove成员，已改为parentNode.removeChild；原失败日志留ignored，不涉及产品修改。该夹具只证明CSS稳定态和检测器，不能代替Master真实工作台目标浏览器复验，更不能要求重跑后端已通过门禁。

永久廉价复跑命令（项目已有精确Node/pnpm与Edge依赖；未安装新包）：

```text
node .tools/pnpm/package/bin/pnpm.cjs --dir apps/web exec playwright test --config playwright.layout.config.ts
node .tools/pnpm/package/bin/pnpm.cjs --dir apps/web exec eslint tests/ui/mobile-navigation.spec.ts playwright.layout.config.ts
node .tools/pnpm/package/bin/pnpm.cjs --dir apps/web run typecheck
```

三条均实际exit0，最终diff-check须exit0。Master拥有的真实API截图采集脚本需另提交正确等待/animations参数与新截图；本切片不把静态CSS夹具声明为真实M5移动验收已完成。
