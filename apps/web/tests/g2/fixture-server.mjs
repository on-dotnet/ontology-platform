import { createServer } from "node:http";
// 仅SSR身份有界夹具；产品接口不挂载此server，不含认证材料。
createServer((request, response) => {
  if (request.url === "/api/v1/platform/me") {
    response.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
    response.end(JSON.stringify({ subjectId: "g2-ui-fixture", displayName: "合成界面测试身份", roles: ["platform.viewer", "platform.operator", "platform.auditor"], scopes: [{ organizationId: "org-demo", siteId: "site-a" }, { organizationId: "org-demo", siteId: "site-b" }] }));
  } else { response.writeHead(404); response.end(); }
}).listen(15810, "127.0.0.1");
