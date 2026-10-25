/** 从部署配置读取固定可信 API 源，绝不使用请求 Host 构造上游。 */
export function getApiOrigin(): string {
  const value = process.env.PLATFORM_API_ORIGIN ?? "http://localhost:15100";
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error("PLATFORM_API_ORIGIN 必须为无凭证的 HTTP(S) 源");
  if (process.env.NODE_ENV === "production" && url.protocol !== "https:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) throw new Error("非回环生产 API 必须使用 HTTPS");
  return url.origin;
}
