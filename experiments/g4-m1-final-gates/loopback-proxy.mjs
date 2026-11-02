import net from 'node:net';
// 仅将共享API/Web命名空间的固定回环OIDC端口转发到本任务身份服务；不提供通用代理。
const server = net.createServer((client) => {
  const upstream = net.connect({ host: 'keycloak-test', port: 8080 });
  client.setTimeout(30000, () => client.destroy());
  upstream.setTimeout(30000, () => upstream.destroy());
  client.on('error', () => upstream.destroy());
  upstream.on('error', () => client.destroy());
  client.on('close', () => upstream.destroy());
  upstream.on('close', () => client.destroy());
  client.pipe(upstream).pipe(client);
});
server.maxConnections = 64;
server.listen(15180, '0.0.0.0');
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => server.close(() => process.exit(0)));
