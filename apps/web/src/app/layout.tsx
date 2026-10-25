import type { Metadata } from "next";
import "../styles/globals.css";
export const metadata: Metadata = { title: "Ontology Platform · 平台工作台", description: "可信语义平台 · 开发资源与访问治理" };
const themeScript = `(function(){try{document.documentElement.dataset.theme=localStorage.getItem('ontology-theme')==='light'?'light':'dark'}catch{document.documentElement.dataset.theme='dark'}})()`;
/** 统一中文文档与首屏主题，避免服务端和浏览器的主题闪烁。 */
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN" suppressHydrationWarning>
    <head>
      <script dangerouslySetInnerHTML={{ __html: themeScript }} />
    </head>
    <body>
      <a className="skip-link" href="#main">跳到主内容</a>{children}</body>
  </html>;
}
