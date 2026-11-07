/** 任务独占HTTPS源；只读本地合成控制，不记录密钥、Header或正文。 */
import https from 'node:https';
import tls from 'node:tls';
import fs from 'node:fs';
const dir='/fixture';
if(process.env.TASK_ID!=='G4-M2-WEB-01'||!/^m2-[a-f0-9]{12}$/.test(process.env.RUN_ID??''))process.exit(2);
const read=name=>fs.readFileSync(`${dir}/${name}`);
const mode=()=>JSON.parse(read('control.json')).mode;
const stats={requests:0,authRejected:0,aborted:0,connections:0,closedSockets:0,sni:[]};
function save(){fs.writeFileSync(`${dir}/stats.tmp`,JSON.stringify(stats));fs.renameSync(`${dir}/stats.tmp`,`${dir}/stats.json`);}
const contexts=Object.fromEntries(['server','wrong-san','wrong-ca'].map(name=>[name,tls.createSecureContext({key:read(`${name}.key`),cert:read(`${name}.crt`)})]));
const server=https.createServer({key:read('server.key'),cert:read('server.crt'),SNICallback:(name,done)=>{stats.sni.push(name==='web-source'?'web-source':'OTHER');save();const variant=mode();done(null,contexts[variant]??contexts.server);}},(req,res)=>{
 stats.requests++;save();
 res.on('close',()=>{if(!res.writableEnded){stats.aborted++;save();}});
 if(req.method!=='GET'||req.url!=='/v1/items'){res.writeHead(404);res.end();return;}
 if(req.headers['x-fixture-api-key']!==read('api-key').toString().trim()){stats.authRejected++;save();res.writeHead(401);res.end();return;}
 const current=mode();
 if(current==='redirect'){res.writeHead(302,{Location:'https://169.254.169.254/key-theft'});res.end();return;}
 if(current==='stall-headers'){const timer=setTimeout(()=>res.end(),30000);res.on('close',()=>clearTimeout(timer));return;}
 res.writeHead(200,{'Content-Type':'application/json'});
 if(current==='stall-body'){res.write('[');const timer=setTimeout(()=>res.end(']'),30000);res.on('close',()=>clearTimeout(timer));return;}
 if(current==='oversize'){res.end('['+' '.repeat(2*1024*1024)+']');return;}
 if(current==='deep'){res.end('['.repeat(24)+']'.repeat(24));return;}
 if(current==='missing'){res.end('[{"id":1,"label":"synthetic"}]');return;}
 if(current==='null-id'){res.end('[{"id":null,"label":"synthetic","reading":1}]');return;}
 if(current==='duplicate'){res.end('[{"id":1,"id":2,"label":"synthetic","reading":1}]');return;}
 res.end('[{"id":9007199254740993123456789,"label":"synthetic","reading":1.2345678901234567890123456789}]');
});
server.on('connection',socket=>{stats.connections++;save();socket.on('close',()=>{stats.closedSockets++;save();});});
server.on('tlsClientError',()=>{});
server.requestTimeout=35000;server.headersTimeout=5000;server.maxConnections=8;
server.listen(8443,'0.0.0.0',save);
