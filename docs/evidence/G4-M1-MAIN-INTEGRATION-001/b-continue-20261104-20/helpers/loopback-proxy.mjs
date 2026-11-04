import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const root=process.env.G4_ROOT, run=process.env.G4_RUN_ID;
if(root!=="/Users/chasen/.codex/worktrees/g4-m1-main-integration-001/ontology-platform" || !/^b-continue-[0-9]{8}-[0-9]{2}$/.test(run)) process.exit(2);
const server=net.createServer(client=>{
  const remote=net.connect({host:'keycloak-test',port:8080});
  client.on('error',()=>remote.destroy()); remote.on('error',()=>client.destroy());
  client.pipe(remote);remote.pipe(client);
});
server.listen(15180,'127.0.0.1');
const dir=path.join(root,'apps/web');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'.next/required-server-files.json'),'utf8'));
process.env.__NEXT_PRIVATE_STANDALONE_CONFIG=JSON.stringify(manifest.config);
process.chdir(dir);
const require=createRequire(path.join(dir,'package.json'));
await require('next/dist/server/lib/start-server').startServer({dir,hostname:'0.0.0.0',port:15300,isDev:false,allowRetry:false,keepAliveTimeout:5000});
