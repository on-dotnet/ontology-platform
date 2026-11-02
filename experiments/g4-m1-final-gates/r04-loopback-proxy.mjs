import net from 'node:net';
// 固定三条内部服务映射，API 保持原冻结回环合同，无外网或用户可选目标。
const servers = [[15180,'keycloak-test',8080],[15303,'fuseki',3030],[15900,'rustfs',9000]].map(([port,host,target]) => {
  const server=net.createServer(client=>{
    const upstream=net.connect({host,port:target});
    client.setTimeout(30000,()=>client.destroy());upstream.setTimeout(30000,()=>upstream.destroy());
    client.on('error',()=>upstream.destroy());upstream.on('error',()=>client.destroy());
    client.on('close',()=>upstream.destroy());upstream.on('close',()=>client.destroy());
    client.pipe(upstream).pipe(client);
  });server.maxConnections=64;server.listen(port,'127.0.0.1');return server;
});
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{for(const server of servers)server.close();setTimeout(()=>process.exit(0),1000).unref();});
