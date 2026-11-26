// PreToolUse hook for Bash and PowerShell: blocks `dev.ps1 reset` everywhere and
// `dev.ps1 down` inside a git worktree. Exit 2 blocks the tool call; any internal
// error exits 0 so a broken hook never blocks every command (deny rules remain the floor).
import { statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

// Plain text match, no shell parsing: the existing deny rules miss spellings such as
// `.\dev.ps1 reset` or `pwsh -File dev.ps1 reset`, so err on the side of blocking.
// The optional quotes cover `"C:\path\dev.ps1" reset` and `dev.ps1 'reset'`; `[\\/]dev`
// covers PowerShell resolving `./dev` to dev.ps1; the switch group covers
// `dev.ps1 -Command reset`; the lookahead keeps `downgrade` or `test_download.py` from matching.
const VERB = /(?:dev\.ps1|[\\/]dev)['"]?(?:\s+-\w+)*\s+['"]?(reset|down)(?![\w-])/gi;

// Sessions otherwise retry the same text; say why a mere mention is blocked too.
const HINT = '提示：钩子按文本匹配，命令里只是提到这几个词（例如搜索或提交信息）也会被拦；搜索请用 Grep 工具，长文本先写进文件再用 -F 传入。';

function findVerbs(command) {
  const verbs = new Set();
  for (const m of command.matchAll(VERB)) verbs.add(m[1].toLowerCase());
  return verbs;
}

// 'worktree' when the nearest .git is a file, 'main' when it is a directory, null otherwise.
function checkoutKind(cwd) {
  let dir = resolve(cwd);
  for (;;) {
    let st;
    try {
      st = statSync(join(dir, '.git'));
    } catch {
      st = null;
    }
    if (st) {
      if (st.isFile()) return 'worktree';
      if (st.isDirectory()) return 'main';
      return null;
    }
    const parent = dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function decide(input) {
  const command = input?.tool_input?.command;
  if (typeof command !== 'string') return null;
  const verbs = findVerbs(command);
  if (verbs.has('reset')) {
    return [
      '已拦截：命令里含有 `dev.ps1 reset`。',
      '原因：reset 会删除开发栈的数据卷，只能由用户本人运行。',
      '怎么办：停下来，告诉用户需要 reset 及原因，由用户本人在主检出目录运行。',
      HINT,
      `命令原文：${command}`,
    ].join('\n');
  }
  if (verbs.has('down') && typeof input.cwd === 'string' && checkoutKind(input.cwd) === 'worktree') {
    return [
      '已拦截：在 git worktree 里运行 `dev.ps1 down`。',
      '原因：开发栈只有一套，postgres 共用，在 worktree 里停掉会中断其他会话的测试和用户正在用的开发栈。',
      '怎么办：不要在 worktree 里 down；确实需要时，请主会话或用户到主检出目录运行 `./dev.ps1 down`。',
      HINT,
      `命令原文：${command}`,
    ].join('\n');
  }
  return null;
}

async function main() {
  try {
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    const input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    const message = decide(input);
    if (message) {
      process.stderr.write(message + '\n');
      process.exitCode = 2;
      return;
    }
  } catch {
    // Fail open: see header comment.
  }
  process.exitCode = 0;
}

// No "run only when invoked as a script" guard: comparing argv[1] with import.meta.url can
// differ through junctions or short paths, which would turn the hook into a silent no-op.
await main();
