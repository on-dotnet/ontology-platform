import { createServer } from "node:http";
// 仅隔离浏览器测试使用，绝不注册到产品路由或生产启动脚本。
createServer((request, response) => {
  if (request.url === "/api/v1/platform/me") {
    response.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
    response.end(JSON.stringify({ subjectId: "ui-fixture", displayName: "界面测试身份", roles: ["platform.viewer"], scopes: [{ organizationId: "org-demo", siteId: "site-a" }] }));
  } else { response.writeHead(404); response.end(); }
}).listen(15410, "127.0.0.1");
