import net from 'node:net';
// 固定任务容器内回环端口；原始字节仅走stdin/stdout，不记录HTTP或认证材料。
const port = Number(process.argv[2]);
if (![15100, 15180].includes(port) || process.argv.length !== 3) process.exit(2);
const socket = net.connect({ host: '127.0.0.1', port });
const deadline = setTimeout(() => finish(), 30000);
let closing = false;
function finish() {
  if (closing) return;
  closing = true;
  clearTimeout(deadline);
  socket.destroy();
  process.stdin.destroy();
  process.stdout.end(() => process.exit(0));
  setTimeout(() => process.exit(0), 500).unref();
}
process.stdin.pipe(socket).pipe(process.stdout);
for (const stream of [socket, process.stdin, process.stdout]) stream.on('error', finish);
socket.on('close', finish);
process.stdin.on('end', finish);
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, finish);
