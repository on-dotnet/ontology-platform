import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Trace } from "./semantic-feedback";

describe("真实关联标识的本地Tempo定位入口", () => {
  it.each([
    "0123456789abcdef0123456789abcdef",
    "0123456789ABCDEF0123456789ABCDEF",
  ])("有效32位十六进制标识打开对应Trace查询：%s", traceId => {
    const html = renderToStaticMarkup(createElement(Trace, { traceId }));
    const href = html.match(/href="([^"]+)"/)?.[1]?.replaceAll("&amp;", "&");
    expect(href).toBeDefined();
    const url = new URL(href!);
    expect(url.origin).toBe("http://localhost:15330");
    expect(url.pathname).toBe("/explore");
    expect(url.username).toBe("");
    expect(url.password).toBe("");
    expect(url.hash).toBe("");
    expect([...url.searchParams.keys()].sort()).toEqual(["orgId", "panes", "schemaVersion"]);
    expect(url.searchParams.get("schemaVersion")).toBe("1");
    expect(url.searchParams.get("orgId")).toBe("1");
    expect(JSON.parse(url.searchParams.get("panes")!)).toEqual({
      trace: {
        datasource: "platform-tempo",
        queries: [{
          refId: "A",
          datasource: { uid: "platform-tempo", type: "tempo" },
          queryType: "traceql",
          query: "0123456789abcdef0123456789abcdef",
        }],
        range: { from: "now-24h", to: "now" },
      },
    });
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noreferrer"');
    expect(html).toContain("复制关联标识");
  });

  it.each([
    "", "0".repeat(32), "a".repeat(31), "a".repeat(33), "g".repeat(32),
    " 0123456789abcdef0123456789abcdef", "0123456789abcdef0123456789abcdef\n",
    "0123456789abcdef0123456789abcdef?token=synthetic",
    "https://example.invalid/trace", '0123456789abcdef0123456789abcdef"><script>',
    "%30".repeat(32), "Ａ".repeat(32),
  ])("无效标识不产生任何Grafana导航：%s", traceId => {
    const html = renderToStaticMarkup(createElement(Trace, { traceId }));
    expect(html).not.toContain("href=");
    expect(html).toContain("关联标识格式无效，无法定位链路");
    expect(html).toContain("复制关联标识");
    expect(html).not.toContain("<script>");
  });
});
