import net from 'node:net';
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
// 两个已批准回环入口通过固定docker exec管道承载真实TCP；不授予容器外网。
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const containerId = process.argv[2];
if (process.argv.length !== 3 || !/^[a-f0-9]{64}$/.test(containerId ?? '')) process.exit(2);
const inspect = JSON.parse(execFileSync('docker', ['--context', 'desktop-linux', 'inspect', containerId], { encoding: 'utf8', maxBuffer: 1024 * 1024 }))[0];
if (inspect.Config.Labels['ontology.task-id'] !== 'G4-M1-FINAL-GATES-001' || inspect.Config.Labels['ontology.run-id'] !== 'final-gates-20261102-r04-final' || inspect.Name !== '/ontology-g4-m1-final-gates-001-r04-final-web-1' || !inspect.State.Running || !inspect.HostConfig.NetworkMode.startsWith('container:')) process.exit(2);
const image = JSON.parse(execFileSync('docker', ['--context', 'desktop-linux', 'image', 'inspect', inspect.Image], { encoding: 'utf8', maxBuffer: 1024 * 1024 }))[0];
if (image.Descriptor.digest !== 'sha256:a52166d89cfcc66ea62d10535ca712d161cece5d77ff4cfa758866b6b75ccb3f' || image.Os !== 'linux' || image.Architecture !== 'arm64') process.exit(2);
const apiId = inspect.HostConfig.NetworkMode.slice('container:'.length);
const api = JSON.parse(execFileSync('docker', ['--context', 'desktop-linux', 'inspect', apiId], { encoding: 'utf8', maxBuffer: 1024 * 1024 }))[0];
if (api.Name !== '/ontology-g4-m1-final-gates-001-r04-final-api-1' || api.Config.Labels['ontology.task-id'] !== 'G4-M1-FINAL-GATES-001' || api.Config.Labels['ontology.run-id'] !== 'final-gates-20261102-r04-final') process.exit(2);
const active = new Set();
const servers = [];
let closing = false;
const receipt = path.join(root, `artifacts/g4-m1-final-gates-001/r04-final/host-ingress-process-${process.pid}.json`);
const events = path.join(root, 'artifacts/g4-m1-final-gates-001/r04-final/host-ingress-events.jsonl');
function event(name, details = {}) { fs.appendFileSync(events, JSON.stringify({ utc: new Date().toISOString(), pid: process.pid, event: name, ...details }) + '\n'); }
let listening = 0;
fs.writeFileSync(receipt, JSON.stringify({ taskId: 'G4-M1-FINAL-GATES-001', pid: process.pid, containerId, apiId, ports: [15100, 15180], bind: '127.0.0.1', maxConcurrent: 8, absoluteConnectionSeconds: 30, processMaxSeconds: 7200, startedUtc: new Date().toISOString() }, null, 2), { flag: 'wx' });
function shutdown(exitCode = 0) {
  if (closing) return;
  closing = true;
  process.exitCode = exitCode;
  event('stopping', { exitCode });
  for (const server of servers) server.close();
  for (const item of active) item.finish();
  setTimeout(() => process.exit(exitCode), 1000).unref();
}
for (const port of [15100, 15180]) {
  const server = net.createServer((client) => {
    if (closing || active.size >= 8) { event('connection_refused_limit'); return client.destroy(); }
    const child = spawn('docker', ['--context', 'desktop-linux', 'exec', '-i', containerId, 'node', '--max-old-space-size=32', '/run/stdio-relay.mjs', String(port)], { stdio: ['pipe', 'pipe', 'ignore'] });
    let finished = false;
    const deadline = setTimeout(finish, 30000);
    const item = { finish };
    active.add(item);
    event('child_started', { childPid: child.pid, port, active: active.size });
    function finish() {
      if (finished) return;
      finished = true;
      clearTimeout(deadline);
      client.destroy();
      child.stdin.destroy();
      if (child.exitCode === null) {
        child.kill('SIGTERM');
        setTimeout(() => { if (child.exitCode === null) child.kill('SIGKILL'); }, 500).unref();
      }
    }
    client.pipe(child.stdin);
    child.stdout.pipe(client);
    for (const stream of [client, child.stdin, child.stdout]) stream.on('error', finish);
    client.on('close', finish);
    child.on('error', finish);
    child.on('close', (code, signal) => { finish(); active.delete(item); event('child_closed', { childPid: child.pid, code, signal, active: active.size }); });
  });
  server.on('error', () => { event('bind_failed', { port, code: 'LOOPBACK_BIND_FAILED' }); shutdown(1); });
  server.on('listening', () => { if (++listening === 2) event('ready', { ports: [15100, 15180], bind: '127.0.0.1' }); });
  server.listen(port, '127.0.0.1');
  servers.push(server);
}
process.on('exit', (code) => event('stopped', { exitCode: code, remainingChildren: active.size }));
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => shutdown(0));
setTimeout(shutdown, 7200000).unref();
