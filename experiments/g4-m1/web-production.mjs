import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
// 使用同一真实生产构建记录的序列化配置，与Next生成的standalone入口一致，避免运行时再次编译TS配置。
const dir = process.argv[2];
if (process.argv.length !== 3 || !dir?.endsWith('/g4-m1-recovery-001/ontology-platform/apps/web')) process.exit(2);
const manifest = JSON.parse(fs.readFileSync(path.join(dir, '.next/required-server-files.json'), 'utf8'));
process.env.NODE_ENV = 'production';
process.env.NEXT_TELEMETRY_DISABLED = '1';
process.env.__NEXT_PRIVATE_STANDALONE_CONFIG = JSON.stringify(manifest.config);
process.chdir(dir);
const require = createRequire(path.join(dir, 'package.json'));
const { startServer } = require('next/dist/server/lib/start-server');
await startServer({ dir, hostname: '127.0.0.1', port: 15300, isDev: false, allowRetry: false, keepAliveTimeout: 5000 });
