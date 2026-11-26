// Run with: node --test .claude/hooks/
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const script = join(dirname(fileURLToPath(import.meta.url)), 'guard-dev-commands.mjs');

let root;
let mainCheckout;
let worktree;
let noRepo;

before(() => {
  root = mkdtempSync(join(tmpdir(), 'op-hook-test-'));
  // Main checkout: .git is a directory.
  mainCheckout = join(root, 'main');
  mkdirSync(join(mainCheckout, '.git'), { recursive: true });
  mkdirSync(join(mainCheckout, 'backend'), { recursive: true });
  // Worktree nested under the main checkout, like .claude/worktrees/<name>: .git is a file.
  worktree = join(mainCheckout, '.claude', 'worktrees', 'wt');
  mkdirSync(join(worktree, 'web'), { recursive: true });
  writeFileSync(join(worktree, '.git'), 'gitdir: ../../../.git/worktrees/wt\n');
  noRepo = join(root, 'plain');
  mkdirSync(noRepo);
});

after(() => {
  rmSync(root, { recursive: true, force: true });
});

function run(stdin) {
  const r = spawnSync(process.execPath, [script], { input: stdin, encoding: 'utf8' });
  return { code: r.status, stderr: r.stderr };
}

function hookInput(tool, command, cwd) {
  const input = { session_id: 't', hook_event_name: 'PreToolUse', tool_name: tool, tool_input: { command } };
  if (cwd !== undefined) input.cwd = cwd;
  return JSON.stringify(input);
}

for (const tool of ['Bash', 'PowerShell']) {
  test(`${tool}: down in a worktree is blocked`, () => {
    for (const cmd of ['./dev.ps1 down', '.\\dev.ps1 down', 'pwsh -File dev.ps1 down', '& "C:/x y/dev.ps1" down', './DEV.PS1 Down', './dev.ps1 "down"']) {
      const r = run(hookInput(tool, cmd, worktree));
      assert.equal(r.code, 2, cmd);
      assert.match(r.stderr, /down/);
      assert.match(r.stderr, /主检出目录/);
    }
  });

  test(`${tool}: down in a worktree subdirectory is blocked`, () => {
    assert.equal(run(hookInput(tool, './dev.ps1 down', join(worktree, 'web'))).code, 2);
  });

  test(`${tool}: down in the main checkout is allowed`, () => {
    assert.equal(run(hookInput(tool, './dev.ps1 down', mainCheckout)).code, 0);
    assert.equal(run(hookInput(tool, './dev.ps1 down', join(mainCheckout, 'backend'))).code, 0);
  });

  test(`${tool}: reset is blocked in any directory`, () => {
    for (const cwd of [worktree, mainCheckout, noRepo]) {
      for (const cmd of ['./dev.ps1 reset', '.\\dev.ps1 reset', 'pwsh -File dev.ps1 reset', 'pwsh -File "C:\\repo\\dev.ps1" reset', "& './dev.ps1' reset", "./dev.ps1 'reset'"]) {
        const r = run(hookInput(tool, cmd, cwd));
        assert.equal(r.code, 2, `${cmd} @ ${cwd}`);
        assert.match(r.stderr, /reset/);
        assert.match(r.stderr, /用户本人/);
      }
    }
  });

  test(`${tool}: unrelated dev.ps1 commands are allowed in a worktree`, () => {
    for (const cmd of [
      './dev.ps1 up',
      './dev.ps1 test-api tests/test_download.py',
      './dev.ps1 logs api',
      './dev.ps1 ci -Report',
      './dev.ps1 status',
      './dev.ps1 downgrade',
      './dev.ps1 reset-foo',
      'git log --oneline',
    ]) {
      assert.equal(run(hookInput(tool, cmd, worktree)).code, 0, cmd);
    }
  });

  test(`${tool}: text mentioning down is blocked conservatively in a worktree`, () => {
    assert.equal(run(hookInput(tool, "Write-Output './dev.ps1 down'", worktree)).code, 2);
  });
}

test('invalid JSON is allowed', () => {
  assert.equal(run('not json{').code, 0);
  assert.equal(run('').code, 0);
});

test('missing cwd: down is allowed, reset still blocked', () => {
  assert.equal(run(hookInput('Bash', './dev.ps1 down', undefined)).code, 0);
  // reset does not depend on cwd, so it is blocked even without it.
  assert.equal(run(hookInput('Bash', './dev.ps1 reset', undefined)).code, 2);
});

test('missing command field is allowed', () => {
  assert.equal(run(JSON.stringify({ tool_name: 'Bash', cwd: worktree, tool_input: {} })).code, 0);
  assert.equal(run(JSON.stringify({ tool_name: 'Bash', cwd: worktree })).code, 0);
  assert.equal(run(JSON.stringify({ tool_name: 'Bash', cwd: worktree, tool_input: { command: 42 } })).code, 0);
});

test('down outside any git repository is allowed', () => {
  assert.equal(run(hookInput('Bash', './dev.ps1 down', noRepo)).code, 0);
});

test('nonexistent cwd is allowed for down', () => {
  assert.equal(run(hookInput('Bash', './dev.ps1 down', join(root, 'missing', 'dir'))).code, 0);
});
