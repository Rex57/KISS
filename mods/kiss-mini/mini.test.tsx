import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const BAND = {
  plugin: 'kiss',
  component: 'AbovePrompt',
  props: { hasSurvey: false, isWorking: false, maxRows: 12, bodyColumns: 100, scroll: { offset: 0, bodyRows: 12 }, view: {} },
} as const
// 2 Nov 2026, 14:30:05 UTC: the task id is 1102-143005.
const NOW = Date.UTC(2026, 10, 2, 14, 30, 5)
const ID = '1102-143005'

/** The engine beneath the mod: one session that is both the sender and the host. */
type Opts = {
  delivered?: boolean
  branch?: string
  fail?: Record<string, { stdout?: string; stderr?: string }>
  store?: Record<string, unknown>
  /** argv[0] values, or git verbs as `branch -D`, whose run rejects, as a timed-out or missing command does. */
  hang?: string[]
  tmp?: string
  cwd?: string
  /** What `claude plugin list --json` answers: the installed plugins. */
  plugins?: { id: string; enabled: boolean; installPath: string; readFromFolder?: string }[]
  /** The checkout has a CodeGraph index: `codegraph status <it>` names it as its project. */
  indexed?: boolean
  /** The repo's root, as `git rev-parse --show-toplevel` answers it (default: cwd). */
  top?: string
  /** How long `codegraph explore` (the seed) takes, on the mock clock. */
  seedMs?: number
}
function world(on: On, { delivered = true, branch = 'main', fail = {}, store, hang = [], tmp = '/tmp/', cwd = '/repo', plugins = [], indexed = false, top = cwd, seedMs = 0 }: Opts = {}) {
  const w = {
    session: 's1',
    branch,
    /** A merge under way in the checkout (MERGE_HEAD): the owner's own, or a failed merge's. */
    merging: false,
    /** The task's branch is in its base (merged by the harness or by hand). */
    merged: false,
    /** Commits on the worker's branch past its base, and what `git status --porcelain` says in its worktree. */
    ahead: 1,
    dirty: '',
    clock: undefined as unknown as ReturnType<typeof mock.clock>,
    /** What `gh pr view` and `gh run view` answer, and the clock time of each gh call. */
    gh: { pr: 'OPEN', run: 'in_progress ' },
    ghAt: [] as number[],
    models: 0,
    opened: [] as string[],
    /** What `$.agent.list()` answers: the host's agents and where each loop stands. */
    agents: [] as { id: string; description: string; type: string; status: string }[],
    store: {} as Record<string, any>,
    sent: [] as { to: string; text: string }[],
    spawned: [] as { prompt: string; subagentType?: string; cwd?: string }[],
    runs: [] as string[][],
    toasts: [] as string[],
    files: {} as Record<string, string>,
    commands: [] as string[],
    /** The store's reads throw, as a store that is gone does. */
    storeDown: false,
    /** Folders that no longer exist: a git -C there fails as git does. */
    gone: [] as string[],
    /** The task's branch is already deleted: `git branch --list` names nothing. */
    branchGone: false,
  }
  w.clock = mock.clock(on, { now: NOW })
  // The store in memory, readable by the test: the ledger is the contract every session reads.
  const mem: Record<string, unknown> = JSON.parse(JSON.stringify(store ?? {}))
  w.store = mem
  on('store.get', ($, e) => ({ value: mem[e.key] }) as never)
  on('store.set', ($, e) => ((mem[e.key] = JSON.parse(JSON.stringify(e.value))), { value: undefined }) as never)
  on('store.delete', ($, e) => (delete mem[e.key], { value: undefined }) as never)
  on('store.keys', () => {
    if (w.storeDown) throw new Error('store down')
    return { value: Object.keys(mem) } as never
  })
  mock.env(on, { KISS_MINI_HOST: '1', TMPDIR: tmp })
  on('session.id', () => ({ value: w.session }))
  on('session.cwd', () => ({ value: cwd }))
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('command.register', ($, e) => (w.commands.push(e.name), { value: { command: e.name } }) as never)
  on('session.send', ($, e) => {
    w.sent.push({ to: e.to, text: e.text })
    return delivered ? { isDelivered: true } : { isDelivered: false, reason: 'no live session' }
  })
  on('agent.spawn', ($, e) => {
    // Beneath the plugins the spawn is the Agent tool's call, spelled as the tool takes it.
    const call = e as unknown as { prompt: string; subagent_type?: string; cwd?: string }
    w.spawned.push({ prompt: call.prompt, subagentType: call.subagent_type, cwd: call.cwd })
    return { model: 'sonnet', agentId: `w${w.spawned.length}` }
  })
  on('process.run', async ($, e) => {
    w.runs.push([...e.argv])
    if (e.argv[0] === 'git' && w.gone.includes(e.argv[2] ?? '')) return { value: { exitCode: 128, stdout: '', stderr: `fatal: cannot change to '${e.argv[2]}': No such file or directory\n`, isStdoutTruncated: false, isStderrTruncated: false } }
    // Every test's repository is /repo; its worktrees share its git folder.
    if (e.argv[3] === 'branch' && e.argv[4] === '--list') return { value: { exitCode: 0, stdout: w.branchGone ? '' : `  ${e.argv[5]}\n`, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv.includes('--git-common-dir')) return { value: { exitCode: 0, stdout: '/repo/.git\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv.includes('--show-toplevel')) return { value: { exitCode: 0, stdout: `${top}\n`, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv[0] === 'codegraph' && e.argv[1] === 'explore' && seedMs) await w.clock.advance(seedMs)
    if (hang.includes(e.argv[0] ?? '') || hang.includes(`${e.argv[3]} ${e.argv[4]}`)) throw new Error(`${e.argv[0]}: timed out after 120000 ms`)
    if (e.argv[0] === 'codegraph') {
      const out = e.argv[1] === 'status' ? (indexed ? `CodeGraph Status\n\nProject: ${top}\n` : 'CodeGraph not initialized\n') : e.argv[1] === 'explore' ? 'SEED: calc.py add()\n' : ''
      return { value: { exitCode: 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    if (e.argv[0] === 'gh' && e.argv[2] === 'view') {
      w.ghAt.push(w.clock.now())
      return { value: { exitCode: 0, stdout: `${e.argv[1] === 'pr' ? w.gh.pr : w.gh.run}\n`, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    if (e.argv[0] === 'sh') {
      const failed = e.argv[2]?.includes('fail')
      return { value: { exitCode: failed ? 1 : 0, stdout: failed ? 'collected 3\nline a\nFAILED test_add - assert -1 == 5\n' : 'ok\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    if (e.argv.includes('rev-list')) return { value: { exitCode: 0, stdout: `${w.ahead}\n`, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv.includes('--porcelain') && e.argv.includes('status')) return { value: { exitCode: 0, stdout: w.dirty, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv.includes('--is-ancestor')) return { value: { exitCode: w.merged ? 0 : 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv.includes('MERGE_HEAD')) return { value: { exitCode: w.merging ? 0 : 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv.includes('--abort')) w.merging = false
    // The checkout is on w.branch; the worker's branch differs from the base by one line; `fail` names git verbs that fail.
    const bad = fail[`${e.argv[3]} ${e.argv[4]}`] ?? fail[e.argv[3] ?? ''] ?? fail[e.argv[0] ?? '']
    if (bad && e.argv[3] === 'merge') w.merging = true
    if (bad) return { value: { exitCode: 1, stdout: bad.stdout ?? '', stderr: bad.stderr ?? '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv.join(' ') === 'claude plugin list --json') return { value: { exitCode: 0, stdout: JSON.stringify(plugins), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    const out = e.argv.includes('--abbrev-ref') ? `${w.branch}\n` : e.argv.includes('--shortstat') ? ' 1 file changed, 1 insertion(+), 1 deletion(-)\n' : ''
    return { value: { exitCode: 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('agent.list', () => ({ value: w.agents }) as never)
  on('model.complete', () => {
    w.models++
    return { value: { isAnswered: true, text: `reads calc.py (${w.models})`, usage: {} } } as never
  })
  on('ui.open', ($, e) => (w.opened.push(e.id), { value: { isPlaced: true } }) as never)
  on('tool.register', ($, e) => ({ value: { tool: `mcp__kiss__${e.name}` } }) as never)
  on('fs.write', ($, e) => {
    w.files[e.path] = e.text
    return { value: undefined }
  })
  on('ui.toast', ($, e) => {
    w.toasts.push(e.text)
    return { value: undefined }
  })
  on('session.receive', ($, e) => ({ text: e.text }))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  // What Claude Code draws above the prompt without the mod.
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>prompt only</Text>
  })
  return w
}

const status = async ($: any) => (await $.command.run({ command: 'kiss:kiss-mini', args: 'status' })).text as string

test('/kiss-mini ask records a working task and the band reads 1 working; the report makes it done with one toast', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'ask what does tickets.py check?' } as never)
  expect(await status($)).toContain(`${ID} question working: what does tickets.py check?`)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  // Until the host takes it, the task waits for a slot.
  expect((await ui.find({ type: 'Text', text: /kiss-mini:/ }))?.text).toBe('kiss-mini: 1 waiting for a slot')

  // The host takes the task in code: the message is consumed, a kiss-worker starts in the sender's folder.
  expect(w.sent.length).toBe(1)
  expect(w.sent[0]?.text).toContain(`KISS-MINI task ${ID}`)
  const got = await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  expect(got.consumed).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /kiss-mini:/ }))?.text).toBe('kiss-mini: 1 working')
  expect(w.spawned.length).toBe(1)
  expect(w.spawned[0]?.subagentType).toBe('kiss:kiss-worker')
  // A question reads the owner's own working tree.
  expect(w.spawned[0]?.cwd).toBe('/repo')
  expect(git(w).some(line => line.includes('worktree add'))).toBe(false)
  expect(w.spawned[0]?.prompt).toContain('mcp__kiss__progress')
  expect(w.spawned[0]?.prompt).toContain('State: done|ready|failed|waiting for you')
  expect(w.spawned[0]?.prompt).toContain('Kind: question')
  expect(w.spawned[0]?.prompt).toContain('what does tickets.py check?')
  expect(w.spawned[0]?.prompt).toContain('Current behaviour:')
  expect(w.spawned[0]?.prompt).toContain('Key interfaces:')

  await $.turn.start({ agentId: 'w1', text: w.spawned[0]?.prompt ?? '', turnId: 't1' })
  await $.turn.complete({
    agentId: 'w1', reason: 'answer', answer: 'State: done\nSummary: It checks the shape of tickets.json.\nBranch: none\nFull log: x\n\nThe whole answer.',
    durationMs: 1000, isAborted: false, turnId: 't1',
  } as never)
  expect(await status($)).toContain(`${ID} question done: what does tickets.py check? - It checks the shape of tickets.json.`)
  expect(w.files[`/tmp/kiss-mini/${ID}/report.md`]).toContain('The whole answer.')
  expect(w.toasts.length).toBe(1)
  expect(await ui.find({ type: 'Text', text: /working/ })).toBeUndefined()
  await ui.unmount()
})

test('/kiss-mini is the skill command (kiss:kiss-mini), answered by the mod; mini is not a registered command', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  expect(w.commands).toEqual([])
  expect(await status($)).toBe('kiss-mini: no tasks.')
})

test('when the send to the host is refused, the mod starts a new host and the task still goes in', async ($, on) => {
  const w = world(on, { delivered: false })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'ask why?' } as never)
  expect(w.spawned.length).toBe(0)
  const start = w.runs.find(argv => argv.includes('--bg'))
  expect(start?.slice(0, 4)).toEqual(['claude', '--bg', '--name', 'kiss-mini'])
  expect(start).toContain(JSON.stringify({ env: { KISS_MINI_HOST: '1' } }))

  // The new host session starts: it takes the task that waits in the ledger.
  w.session = 'h2'
  await $.session.start({ cwd: '/', surface: null, isInteractive: false } as never)
  expect(w.spawned.length).toBe(1)
  expect(w.spawned[0]?.prompt).toContain('why?')
})

// Where Claude Code put KISS for each kind of sender: the host must load it the same way, or it reads another store.
const CACHED = '/u/.claude/plugins/cache/kiss/kiss/2.0.0'
// The plugin under test is this repo: its root is two folders up from this file.
const ROOT = decodeURIComponent(new URL('../..', (import.meta as { url: string }).url).pathname).replace(/\/$/, '')
// The brief names the plugin root (its Rules line): a test of the 1,500 limit pins the paths to an installed KISS's
// root length, so it checks brief(), not the folder this repo is checked out in.
const INSTALLED = '/Users/someone/.claude/plugins/cache/kiss/kiss/2.0.2'
// The cwd and the root each appear once in a brief: a cwd of the length that keeps their sum fixed gives the same brief.
function pin(path: string) {
  const n = path.length + INSTALLED.length - ROOT.length
  if (n < 8) throw new Error(`the checkout's path (${ROOT.length} characters) is too long for this test's cwd`)
  return n <= path.length ? path.slice(0, n) : path + 'x'.repeat(n - path.length)
}
async function hostStart($: any, w: ReturnType<typeof world>) {
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'ask why?' } as never)
  return w.runs.find(argv => argv.includes('--bg')) ?? []
}

test('a sender running KISS installed from a git marketplace (in the plugin cache) starts the host with no --plugin-dir', async ($, on) => {
  const w = world(on, { delivered: false, plugins: [{ id: 'kiss@kiss', enabled: true, installPath: ROOT }] })
  const start = await hostStart($, w)
  expect(start.slice(0, 4)).toEqual(['claude', '--bg', '--name', 'kiss-mini'])
  expect(start).not.toContain('--plugin-dir')
})

test('a sender running KISS installed from a folder marketplace starts the host with no --plugin-dir', async ($, on) => {
  const w = world(on, { delivered: false, plugins: [{ id: 'kiss@kiss', enabled: true, installPath: CACHED, readFromFolder: ROOT }] })
  const start = await hostStart($, w)
  expect(start.slice(0, 4)).toEqual(['claude', '--bg', '--name', 'kiss-mini'])
  expect(start).not.toContain('--plugin-dir')
})

test('a sender still on the KISS version it started with, after an update installed the next, starts the host with no --plugin-dir', async ($, on) => {
  // The session's root names 2.0.0 (here: this repo's folder name); the list names the newly installed version beside it.
  const next = ROOT.replace(/[^/]+$/, '2.0.1')
  const w = world(on, { delivered: false, plugins: [{ id: 'kiss@kiss', enabled: true, installPath: next }] })
  const start = await hostStart($, w)
  expect(start.slice(0, 4)).toEqual(['claude', '--bg', '--name', 'kiss-mini'])
  expect(start).not.toContain('--plugin-dir')
})

test('when claude plugin list fails, the host starts with --plugin-dir <its folder>', async ($, on) => {
  const w = world(on, { delivered: false, fail: { '--json': { stderr: 'x' } }, plugins: [{ id: 'kiss@kiss', enabled: true, installPath: ROOT }] })
  const start = await hostStart($, w)
  expect(start.slice(start.indexOf('--plugin-dir'), start.indexOf('--plugin-dir') + 2)).toEqual(['--plugin-dir', ROOT])
})

test('a --plugin-dir sender starts the host with --plugin-dir <its folder>, also beside an installed KISS', async ($, on) => {
  const w = world(on, {
    delivered: false,
    plugins: [
      { id: 'kiss@kiss', enabled: true, installPath: CACHED },
      { id: 'kiss@dev', enabled: false, installPath: '/u/.claude/plugins/cache/dev/kiss/2.0.0', readFromFolder: ROOT },
    ],
  })
  const start = await hostStart($, w)
  expect(start.slice(start.indexOf('--plugin-dir'), start.indexOf('--plugin-dir') + 2)).toEqual(['--plugin-dir', ROOT])
})

test('with no open task the band draws nothing', async ($, on) => {
  world(on)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ type: 'Text', text: /prompt only/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /kiss-mini:/ })).toBeUndefined()
    await ui.unmount()
  }
})

const PANE = {
  plugin: 'kiss',
  component: 'Pane',
  requestId: 'kiss-mini',
  props: { title: 'kiss-mini', isFocused: true, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 20 }, view: {} },
} as const
const WT = `/tmp/kiss-mini/${ID}/wt`
const READY = [
  'State: ready',
  'Summary: add(a, b) now returns the sum.',
  `Branch: mini/${ID}    Commits: abc1234 fix: add returns the sum`,
  'Tests: python3 -m pytest: 3 passed',
  `Full log: /tmp/kiss-mini/${ID}/report.md`,
  '',
  '## Pull request body',
  'Fixes add.',
].join('\n')

/** A code task from the owner, through the host, to ready. */
async function ready($: any, w: ReturnType<typeof world>) {
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kiss:kiss-mini', args: 'fix add so it returns the sum --base main' })
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' })
  await $.turn.start({ agentId: 'w1', text: w.spawned[0]?.prompt ?? '', turnId: 't1' })
  await $.turn.complete({ agentId: 'w1', reason: 'answer', answer: READY, durationMs: 1000, isAborted: false, turnId: 't1' })
}
const git = (w: ReturnType<typeof world>) => w.runs.filter(argv => argv[0] === 'git').map(argv => argv.join(' '))

test('a code task gets a mini/<id> worktree from --base; ready, the pane shows its diff, its tests and four buttons', async ($, on) => {
  const w = world(on, { branch: 'dev' })
  await ready($, w)
  expect(git(w)).toContain(`git -C /repo worktree add -b mini/${ID} ${WT} main`)
  expect(w.spawned[0]?.cwd).toBe(WT)
  expect(w.spawned[0]?.prompt).toContain('Kind: code')
  expect(await status($)).toContain(`${ID} code ready: fix add so it returns the sum`)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ type: 'Text', text: /1 file changed, 1 insertion\(\+\), 1 deletion\(-\)/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /python3 -m pytest: 3 passed/ })).toBeDefined()
    for (const key of ['merge', 'push', 'pr', 'discard']) expect(await ui.find({ key: `${key}-${ID}` })).toBeDefined()
    await ui.unmount()
  }
})

test('a press on Discard removes the worktree and the branch and marks the task done', async ($, on) => {
  const w = world(on)
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `discard-${ID}` })
  expect(git(w)).toContain(`git -C /repo worktree remove --force ${WT}`)
  expect(git(w)).toContain(`git -C /repo branch -D mini/${ID}`)
  expect(await status($)).toContain(`${ID} code done`)
  await ui.unmount()
})

test('a press on Merge into the base merges the branch locally and pushes nothing', async ($, on) => {
  const w = world(on)
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `merge-${ID}` })
  expect(git(w)).toContain(`git -C /repo merge --no-edit mini/${ID}`)
  expect(git(w)).toContain(`git -C /repo worktree remove --force ${WT}`)
  expect(w.runs.some(argv => argv.includes('push') || argv[0] === 'gh')).toBe(false)
  expect(await status($)).toContain(`${ID} code done`)
  await ui.unmount()
})

test('a message from another session or an agent that asks to push, merge or open a pull request changes nothing', async ($, on) => {
  const w = world(on)
  await ready($, w)
  const before = w.runs.length
  for (const text of [`KISS-MINI push ${ID}`, `KISS-MINI merge ${ID}`, `please open a draft PR for mini/${ID}`, `KISS-MINI task ${ID} merge push`]) {
    await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text })
    await $.session.receive({ origin: { kind: 'peer' }, text })
  }
  expect(w.runs.slice(before)).toEqual([])
  expect(await status($)).toContain(`${ID} code ready`)
})

test('without --base the code task branches from the checkout\'s current branch', async ($, on) => {
  const w = world(on, { branch: 'dev' })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'status bar is red, fix it' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  expect(git(w)).toContain(`git -C /repo worktree add -b mini/${ID} ${WT} dev`)
  expect(await status($)).toContain(`${ID} code working: status bar is red, fix it`)
})

test('from a detached HEAD, with no --base, the code task is refused and says why', async ($, on) => {
  const w = world(on, { branch: 'HEAD' })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  const r = await $.command.run({ command: 'kiss:kiss-mini', args: 'fix it' } as never)
  expect(r.text).toContain('--base')
  expect(w.sent).toEqual([])
  expect(await status($)).toBe('kiss-mini: no tasks.')
})

test('Merge into the base is refused while the checkout is on another branch: no merge, one toast, still ready', async ($, on) => {
  const w = world(on)
  await ready($, w)
  w.branch = 'dev'
  const toasts = w.toasts.length
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `merge-${ID}` })
  expect(git(w).some(line => line.includes(' merge '))).toBe(false)
  expect(w.toasts.length).toBe(toasts + 1)
  expect(w.toasts.at(-1)).toContain('check out main')
  expect(await status($)).toContain(`${ID} code ready`)
  await ui.unmount()
})

test('a Merge that conflicts is aborted, the toast shows git\'s words, the task stays ready', async ($, on) => {
  const w = world(on, { fail: { merge: { stdout: 'CONFLICT (content): Merge conflict in calc.py' } } })
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `merge-${ID}` })
  expect(git(w)).toContain('git -C /repo merge --abort')
  expect(w.toasts.at(-1)).toContain('CONFLICT (content): Merge conflict in calc.py')
  expect(git(w).some(line => line.includes('worktree remove'))).toBe(false)
  expect(await status($)).toContain(`${ID} code ready`)
  await ui.unmount()
})

test('Draft PR pushes the branch and opens a draft PR with the report\'s body; nothing merges', async ($, on) => {
  const w = world(on)
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `pr-${ID}` })
  expect(git(w)).toContain(`git -C /repo push -u origin mini/${ID}`)
  const gh = w.runs.find(argv => argv[0] === 'gh')
  expect(gh).toEqual(['gh', 'pr', 'create', '--draft', '--base', 'main', '--head', `mini/${ID}`, '--title', 'fix add so it returns the sum', '--body', 'Fixes add.'])
  expect(git(w).some(line => line.includes(' merge '))).toBe(false)
  expect(await status($)).toContain(`${ID} code done`)
  await ui.unmount()
})

test('Push pushes the branch, opens no PR and merges nothing', async ($, on) => {
  const w = world(on)
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `push-${ID}` })
  expect(git(w)).toContain(`git -C /repo push -u origin mini/${ID}`)
  expect(w.runs.some(argv => argv[0] === 'gh')).toBe(false)
  expect(git(w).some(line => line.includes(' merge '))).toBe(false)
  expect(git(w)).toContain(`git -C /repo worktree remove --force ${WT}`)
  await ui.unmount()
})

test('a code task that failed still offers Discard for its worktree, and only Discard', async ($, on) => {
  const w = world(on)
  await ready($, w)
  await $.turn.complete({ agentId: 'w1', reason: 'answer', answer: 'State: failed\nSummary: tests would not run.', durationMs: 1, isAborted: false, turnId: 't2' } as never)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ key: `merge-${ID}` })).toBeUndefined()
  await ui.press({ key: `discard-${ID}` })
  expect(git(w)).toContain(`git -C /repo branch -D mini/${ID}`)
  await ui.unmount()
})

test('a second press while a delivery runs finds it taken: one push, one PR', async ($, on) => {
  const w = world(on)
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await Promise.all([ui.press({ key: `pr-${ID}` }), ui.press({ key: `pr-${ID}` }).catch(() => undefined)])
  expect(w.runs.filter(argv => argv[0] === 'gh').length).toBe(1)
  expect(git(w).filter(line => line.includes(' push ')).length).toBe(1)
  await ui.unmount()
})

test('a long task text is cut in the brief, which stays at most 1,500 characters; the whole text is in the task folder', async ($, on) => {
  const w = world(on)
  const text = `fix ${'the long description of the bug '.repeat(60)}`.trim()
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: text } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  expect(w.spawned[0]?.prompt.length).toBeLessThanOrEqual(1500)
  expect(w.spawned[0]?.prompt).toContain(`/tmp/kiss-mini/${ID}/task.md`)
  expect(w.files[`/tmp/kiss-mini/${ID}/task.md`]).toBe(text)
})

test('the host refuses a worker\'s git push, git merge and gh pr; other commands and other loops pass', async ($, on) => {
  const w = world(on)
  const ran: string[] = []
  on('tool.call', ($, e) => {
    ran.push(String((e as { command?: string }).command))
    return { result: {}, text: 'ok' } as never
  })
  await ready($, w)
  for (const command of [`git push -u origin mini/${ID}`, 'git -C /repo merge main', 'git -c x=y push', 'gh pr create --draft', 'gh pr merge 12', 'cd x && git push',
    'git --no-pager push origin x', 'git -C/x push', 'gh api -X POST repos/o/r/pulls -f head=x -f base=main',
    'bash -c "git push origin x"', "sh -c 'cd x && git push'", 'eval "git push"', 'git subtree push --prefix d origin b',
    'git -c alias.p=push p origin x', 'bash -lc "git push origin x"', 'gh api -X PUT repos/o/r/pulls/12/merge',
    "bash -e -c 'git push origin x'", "/bin/bash -x -c 'git push'", 'echo "$(git push origin x)"']) {
    const r = await $.tool.call({ tool: 'Bash', command, agentId: 'w1' } as never)
    expect(JSON.stringify(r)).toContain('press in the /kiss-mini pane')
  }
  const allowed = ['git commit -m "docs: how to git push a branch"', 'git commit -m fix', 'git add merge.py', './build.sh && git commit -m "docs: how to git push a branch"', 'git add run.sh && git commit -m "explain git merge in the readme"', 'git commit -m "bash: git merge notes"', 'git commit -m "merge the push docs"', 'git merge-base main HEAD', 'git log --grep merge', 'gh pr view 12']
  for (const command of allowed) await $.tool.call({ tool: 'Bash', command, agentId: 'w1' } as never)
  await $.tool.call({ tool: 'Bash', command: 'git push', agentId: 'other' } as never)
  expect(ran).toEqual([...allowed.map(c => `cd '${WT}' && ${c}`), 'git push'])
})

// D1, D2: a code or bug worker writes only in its worktree WT; /repo (the sender's checkout) is outside it.
const ONLY = 'kiss-mini: a worker writes only in its worktree'
/** A working code task whose worker is w1, and each call that reached beneath the mod: its tool and command or path. */
async function worker($: any, on: On, opts: Opts = {}) {
  const w = world(on, opts)
  const ran: string[] = []
  on('tool.call', ($, e) => {
    const a = e as { command?: string; file_path?: string; notebook_path?: string }
    ran.push(`${String(e.tool)} ${a.command ?? a.file_path ?? a.notebook_path}`)
    return { result: {}, text: 'ok' } as never
  })
  await working($, w)
  return { w, ran }
}
const call = ($: any, tool: string, arg: Record<string, string>, agentId: string | null = 'w1') =>
  $.tool.call({ tool, ...arg, ...(agentId ? { agentId } : {}) } as never)

test('a code worker\'s git command that writes outside its worktree is denied: -C, cd, GIT_DIR, --work-tree, pushd, bash -c', async ($, on) => {
  const { ran } = await worker($, on)
  for (const command of ['git -C /repo commit -m x', 'cd /repo && git reset --hard', 'GIT_DIR=/repo/.git git checkout main',
    'git --work-tree=/repo stash', 'pushd /repo; git rebase main', "bash -c 'git -C /repo merge x'",
    // A quoted folder is still the folder; each -C starts from the one before; --git-dir with its value apart; eval runs its text.
    'git -C "/srv/other repo" commit -m x', `git -C ${WT} -C ../.. reset --hard`, 'git --git-dir /repo/.git commit -m x',
    'eval "cd /repo && git commit -m x"', 'git -C ~/repo commit -m x',
    // Each -C starts from the one before: sub of /repo is outside, sub of the worktree is not.
    'git -C /repo -C sub commit -m x',
    // cd's -- and flags are no folder; cd - goes back to the host's folder, which the mod's cd left.
    'cd -- /repo && git commit -m x', 'pushd -- /repo; git reset --hard', 'cd -P -- /repo && git checkout main', 'cd - && git commit -m x',
    // A shell by its path, and the text after its first flag that holds c.
    "/bin/bash -c 'git -C /repo commit -m x'", "bash -e -c 'git -C /repo commit -m x'", 'sh -x -c "cd /repo && git reset --hard"',
    // $(...) and backtick text inside double quotes runs.
    'echo "$(git -C /repo commit -m x)"', 'msg="$(cd /repo && git reset --hard)"', 'echo "`git -C /repo commit -m x`"']) {
    expect(JSON.stringify(await call($, 'Bash', { command })), command).toContain(ONLY)
  }
  expect(ran).toEqual([])
})

test('a code worker\'s git commands inside its worktree, and its git reads anywhere, pass', async ($, on) => {
  const { ran } = await worker($, on)
  const allowed = ['git commit -m "see /some/other/path"', "git commit -m 'git -C /repo reset'", 'git -C sub commit -m x',
    `git -C ${WT}/sub commit -m x`, `cd ${WT}/sub && git add calc.py`, 'git -C /repo log', 'git -C /repo status', 'git -C /repo diff',
    'GIT_DIR=/repo/.git git show HEAD', 'cd -- sub && git add calc.py', 'echo "$(git -C /repo log -1)"', 'git commit -m "fix: $(date)"']
  for (const command of allowed) await call($, 'Bash', { command })
  expect(ran).toEqual(allowed.map(c => `Bash cd '${WT}' && ${c}`))
})

test('a code worker\'s git stash, git worktree change and --output outside are denied, also from its worktree', async ($, on) => {
  const { ran } = await worker($, on)
  // refs/stash and the worktree list are shared by every worktree; --output writes a file, also from a read verb.
  for (const command of ['git stash', 'git stash pop', `git -C ${WT}/sub stash push -m wip`,
    'git worktree remove --force /repo', 'git worktree add ../other main', 'git worktree prune',
    'git -C /repo diff --output=/repo/calc.py', 'git diff --output /repo/calc.py', `git log --output=${WT}/../x.txt`]) {
    expect(JSON.stringify(await call($, 'Bash', { command })), command).toContain(ONLY)
  }
  const allowed = ['git worktree list', 'git diff --output=out.diff', 'git grep -o add', 'git -C /repo ls-files -o']
  for (const command of allowed) await call($, 'Bash', { command })
  expect(ran).toEqual(allowed.map(c => `Bash cd '${WT}' && ${c}`))
})

test('a worker\'s Bash command runs in its worktree: the mod puts a cd there first, one word with a space or a quote', async ($, on) => {
  // The worker's shell starts in the host's folder (the spawn's cwd does not move it), so a bare git write needs the cd.
  const { ran } = await worker($, on, { tmp: "/tmp/it's a dir/" })
  await call($, 'Bash', { command: 'git commit -m x' })
  expect(JSON.stringify(await call($, 'Bash', { command: 'git -C /repo commit -m x' }))).toContain(ONLY)
  expect(ran).toEqual([`Bash cd '/tmp/it'\\''s a dir/kiss-mini/${ID}/wt' && git commit -m x`])
})

test('a worker\'s command that starts with the brief\'s prefix reaches beneath the mod unchanged; one without gets it once', async ($, on) => {
  // D24: the mod's rewrite makes auto mode review a command again, so the brief names the prefix for the worker to type.
  const { w, ran } = await worker($, on)
  const prefix = `cd '${WT}' && `
  expect(w.spawned[0]?.prompt).toContain(`\nBash: cd '<Worktree>' && <command>\n`)
  for (const command of [`${prefix}git status`, 'pytest -q', `${prefix}cd sub && git add calc.py`]) await call($, 'Bash', { command })
  expect(ran).toEqual([`Bash ${prefix}git status`, `Bash ${prefix}pytest -q`, `Bash ${prefix}cd sub && git add calc.py`])
})

test('a /private/var spelling of a /var worktree is inside it', async ($, on) => {
  const { ran } = await worker($, on, { tmp: '/var/kiss/' })
  const wt = `/private/var/kiss/kiss-mini/${ID}/wt`
  await call($, 'Bash', { command: `git -C ${wt} commit -m x` })
  await call($, 'Write', { file_path: `${wt}/calc.py` })
  expect(ran).toEqual([`Bash cd '/var/kiss/kiss-mini/${ID}/wt' && git -C ${wt} commit -m x`, `Write ${wt}/calc.py`])
})

test('a code worker\'s Edit, Write and NotebookEdit outside its worktree are denied; inside they pass', async ($, on) => {
  const { ran } = await worker($, on)
  for (const tool of ['Edit', 'Write', 'NotebookEdit']) {
    const key = tool === 'NotebookEdit' ? 'notebook_path' : 'file_path'
    for (const path of ['/repo/calc.py', `${WT}/../x.py`, `${WT}-other/x.py`]) {
      expect(JSON.stringify(await call($, tool, { [key]: path })), `${tool} ${path}`).toContain(ONLY)
    }
    await call($, tool, { [key]: `${WT}/calc.py` })
    await call($, tool, { [key]: 'sub/calc.py' })
  }
  expect(ran).toEqual(['Edit', 'Write', 'NotebookEdit'].flatMap(tool => [`${tool} ${WT}/calc.py`, `${tool} sub/calc.py`]))
})

test('the guard leaves the main loop, a subagent that is no task\'s worker and a worker\'s non-git command alone', async ($, on) => {
  const { ran } = await worker($, on)
  const outside = [['Bash', 'command', 'git -C /repo commit -m x'], ['Write', 'file_path', '/repo/x.py']] as const
  for (const agentId of [null, 'other']) for (const [tool, key, value] of outside) await call($, tool, { [key]: value }, agentId)
  await call($, 'Bash', { command: 'python3 /repo/tools/check.py' })
  expect(ran).toEqual([...outside, ...outside].map(([tool, , value]) => `${tool} ${value}`).concat(`Bash cd '${WT}' && python3 /repo/tools/check.py`))
})

test('an error inside the guard (a store read that throws) denies a worker\'s git write and its Write outside', async ($, on) => {
  const { w, ran } = await worker($, on)
  w.storeDown = true
  expect(JSON.stringify(await call($, 'Bash', { command: 'git -C /repo commit -m x' }))).toContain(ONLY)
  expect(JSON.stringify(await call($, 'Write', { file_path: '/repo/x.py' }))).toContain(ONLY)
  await call($, 'Bash', { command: 'git -C /repo log' })
  expect(ran).toEqual(['Bash git -C /repo log'])
})

test('a delivered task keeps no PR body, diff or tests', async ($, on) => {
  const w = world(on)
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `push-${ID}` })
  await ui.unmount()
  // The ledger entry is the contract every session reads.
  const t = w.store[`kiss-mini/task/${ID}`]
  expect(t.state).toBe('done')
  expect([t.pr, t.diff, t.tests]).toEqual([undefined, undefined, undefined])
})

test('the host forgets a task ended over 7 days ago, keeps a newer one and one that still holds a worktree', async ($, on) => {
  const day = 24 * 3600_000
  const old = { kind: 'question', title: 'q', sender: 's0', cwd: '/repo', started: NOW - 9 * day }
  world(on, {
    store: {
      'kiss-mini/task/old': { ...old, id: 'old', state: 'done', finished: NOW - 8 * day },
      'kiss-mini/task/new': { ...old, id: 'new', state: 'done', finished: NOW - 6 * day },
      'kiss-mini/task/wt': { ...old, id: 'wt', kind: 'code', state: 'failed', finished: NOW - 8 * day, worktree: '/tmp/x' },
    },
  })
  await $.session.start({ cwd: '/', surface: null, isInteractive: false } as never)
  const list = await status($)
  expect(list).not.toContain('old ')
  expect(list).toContain('new question done')
  expect(list).toContain('wt code failed')
})

test('Merge is refused while the checkout has a merge of its own under way: no merge, no abort, one toast', async ($, on) => {
  const w = world(on)
  await ready($, w)
  w.merging = true
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `merge-${ID}` })
  expect(git(w).some(line => line.includes(' merge --no-edit') || line.includes('--abort'))).toBe(false)
  expect(w.toasts.at(-1)).toContain(`${ID}: merge failed: a merge is under way in /repo`)
  expect(await status($)).toContain(`${ID} code ready`)
  await ui.unmount()
})

test('a delivery whose command throws is released: one toast, no claim left, the buttons drawn again', async ($, on) => {
  const w = world(on, { hang: ['gh'] })
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `pr-${ID}` })
  expect(w.toasts.at(-1)).toContain(`kiss-mini ${ID}: pr failed`)
  expect(w.store[`kiss-mini/task/${ID}`].busy).toBeUndefined()
  expect(await ui.find({ key: `pr-${ID}` })).toBeDefined()
  expect(await ui.find({ key: `discard-${ID}` })).toBeDefined()
  await ui.unmount()
})

test('a failed worktree add leaves no worktree to Discard, and the task ends with a time', async ($, on) => {
  const w = world(on, { fail: { worktree: { stderr: "fatal: invalid reference: nosuch" } } })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'fix it --base nosuch' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  const t = w.store[`kiss-mini/task/${ID}`]
  expect([t.state, t.worktree, t.branch, t.finished]).toEqual(['failed', undefined, undefined, NOW])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ key: `discard-${ID}` })).toBeUndefined()
  await ui.unmount()
})

test('an ended task that still holds a worktree stays in the pane past the last 10 ended', async ($, on) => {
  const base = { kind: 'question', title: 'q', sender: 's0', cwd: '/repo', started: NOW, state: 'done' }
  const store: Record<string, unknown> = { 'kiss-mini/task/kept': { ...base, id: 'kept', kind: 'code', state: 'failed', worktree: '/tmp/x', branch: 'mini/kept' } }
  for (let i = 0; i < 12; i++) store[`kiss-mini/task/q${i}`] = { ...base, id: `q${i}`, finished: NOW - i }
  world(on, { store })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ key: 'discard-kept' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /q11 question/ })).toBeUndefined()
  await ui.unmount()
})

test('with real-length paths a long task text still gives a brief of at most 1,500 characters', async ($, on) => {
  // Made-up paths as long as a real temp folder and a real session's scratch folder.
  const tmp = '/var/folders/x_/abcdefghijklmnopqrstuvwxyz01/T/'
  const cwd = pin('/home/someone/.cache/agent-501/-home-someone-Projects-Repo-SOMEAPP-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d/scratchpad/run1/repo-0123456789abcdefghij')
  const w = world(on, { tmp, cwd })
  await $.session.start({ cwd, surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: `fix ${'the long bug text '.repeat(30)}`.trim() } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  expect(w.spawned[0]?.prompt.length).toBeLessThanOrEqual(1500)
  expect(w.spawned[0]?.prompt).toContain('task.md')
})

test('Discard clears a worktree git no longer lists, so the task can leave the ledger', async ($, on) => {
  const w = world(on, { fail: { 'worktree remove': { stderr: `fatal: '/tmp/kiss-mini/${ID}/wt' is not a working tree` } } })
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `discard-${ID}` })
  expect(git(w)).toContain(`git -C /repo branch -D mini/${ID}`)
  expect([w.store[`kiss-mini/task/${ID}`].state, w.store[`kiss-mini/task/${ID}`].worktree]).toEqual(['done', undefined])
  expect(w.toasts.some(text => text.includes('worktree kept'))).toBe(false)
  await ui.unmount()
})

// D16: Discard's git runs in the task's own repository (/repo), found from its worktree; a harness task's sender folder
// is the run's worktree, which is gone after the run's merge.
const RUN = '/repo/.kiss/worktrees/run'
const discard = async ($: any, w: ReturnType<typeof world>) => {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `discard-${ID}` })
  const t = w.store[`kiss-mini/task/${ID}`]
  const offered = (await ui.find({ key: `discard-${ID}` })) !== undefined
  await ui.unmount()
  return { t, offered }
}

test('Discard of a harness task whose sender folder is gone removes the worktree and the branch in the task\'s repository', async ($, on) => {
  const w = world(on, { cwd: RUN })
  await handoff($, w, false)
  w.gone.push(RUN)
  const toasts = w.toasts.length
  const { t } = await discard($, w)
  expect(git(w)).toContain(`git -C /repo worktree remove --force ${WT}`)
  expect(git(w)).toContain(`git -C /repo branch -D mini/${ID}`)
  expect([t.state, t.worktree]).toEqual(['done', undefined])
  expect(w.toasts.length).toBe(toasts)
})

test('a harness task merged into its base while its sender folder is gone ends done; its worktree goes in its repository', async ($, on) => {
  const w = world(on, { cwd: RUN })
  await handoff($, w, false)
  w.gone.push(RUN)
  w.merged = true
  await w.clock.advance(60_000)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('done')
  expect(git(w)).toContain(`git -C /repo worktree remove --force ${WT}`)
})

test('Discard whose worktree list fails keeps the task open with its worktree, and toasts git\'s words', async ($, on) => {
  const w = world(on, { fail: { 'worktree remove': { stderr: `fatal: '${WT}' is not a working tree` }, 'worktree list': { stderr: 'fatal: unable to read the worktree list' } } })
  await ready($, w)
  const { t, offered } = await discard($, w)
  expect(w.toasts.at(-1)).toContain('fatal: unable to read the worktree list')
  expect([t.state, t.worktree, t.branch, offered]).toEqual(['ready', WT, `mini/${ID}`, true])
  expect(git(w).some(line => line.includes('branch -D'))).toBe(false)
})

test('Discard whose branch -D fails after the worktree went toasts; the task stays open with its branch and no worktree', async ($, on) => {
  const w = world(on, { fail: { 'branch -D': { stderr: `error: cannot delete branch 'mini/${ID}'` } } })
  await ready($, w)
  const { t, offered } = await discard($, w)
  expect(w.toasts.at(-1)).toContain(`discard failed: error: cannot delete branch 'mini/${ID}'`)
  expect([t.state, t.worktree, t.branch, offered]).toEqual(['ready', undefined, `mini/${ID}`, true])
})

test('a Discard interrupted after the worktree went, with the sender folder gone, finishes on a second press', async ($, on) => {
  const hang = ['branch -D']
  const w = world(on, { cwd: RUN, hang })
  await handoff($, w, false)
  w.gone.push(RUN)
  expect((await discard($, w)).t.state).toBe('ready')
  w.gone.push(WT)
  hang.length = 0
  const { t, offered } = await discard($, w)
  expect(git(w).filter(line => line === `git -C /repo branch -D mini/${ID}`).length).toBe(2)
  expect([t.state, offered]).toEqual(['done', false])
})

test('a Discard whose branch is already deleted (an interrupted press deleted it) ends done', async ($, on) => {
  const w = world(on, { fail: { 'branch -D': { stderr: `error: branch 'mini/${ID}' not found` } } })
  await ready($, w)
  w.branchGone = true
  const toasts = w.toasts.length
  expect((await discard($, w)).t.state).toBe('done')
  expect(w.toasts.length).toBe(toasts)
})

test('Merge of an owner\'s task whose sender folder is gone toasts the missing folder, writes nothing, stays ready', async ($, on) => {
  const w = world(on)
  await ready($, w)
  w.gone.push('/repo')
  const before = git(w).length
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `merge-${ID}` })
  await ui.unmount()
  expect(w.toasts.at(-1)).toContain("merge failed: fatal: cannot change to '/repo': No such file or directory")
  expect(git(w).slice(before).filter(line => !/ rev-parse | diff /.test(line))).toEqual([])
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('ready')
})

const HANDOFF_BRIEF = [
  'Kind: bug',
  'Summary: add() subtracts.',
  'Current behaviour: add(2, 3) gives -1.',
  'Expected behaviour: add(2, 3) gives 5.',
  'Key interfaces: calc.py add()',
  'Acceptance checks:',
  '- python3 -c "from calc import add; assert add(2, 3) == 5"',
  'Out of scope: other functions.',
  'Suggested skills: diagnosing-bugs, tdd',
].join('\n')

async function handoff($: any, w: ReturnType<typeof world>, back: boolean) {
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const r = await $.tool.call({ tool: 'mcp__kiss__handoff', kind: 'bug', title: 'add subtracts', brief: HANDOFF_BRIEF, base: 'kiss-run', return: back })
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' })
  await $.turn.start({ agentId: 'w1', text: w.spawned[0]?.prompt ?? '', turnId: 't1' })
  await $.turn.complete({ agentId: 'w1', reason: 'answer', answer: READY, durationMs: 1000, isAborted: false, turnId: 't1' })
  return r
}

test('a hand-off from the harness branches from the base it names and returns one report in the report format', async ($, on) => {
  const w = world(on, { branch: 'dev' })
  const r = await handoff($, w, true)
  expect(JSON.stringify(r)).toContain(ID)
  expect(git(w)).toContain(`git -C /repo worktree add -b mini/${ID} ${WT} kiss-run`)
  expect(w.spawned[0]?.prompt).toContain('Return: harness')
  expect(w.spawned[0]?.prompt).toContain('Current behaviour: add(2, 3) gives -1.')
  const back = w.sent.filter(m => !m.text.startsWith('KISS-MINI task'))
  expect(back.length).toBe(1)
  expect(back[0]?.to).toContain('s1')
  const text = back[0]?.text ?? ''
  expect(text).toContain('State: ready')
  expect(text).toContain('Summary: add(a, b) now returns the sum.')
  expect(text).toContain(`Branch: mini/${ID}    Commits: abc1234 fix: add returns the sum`)
  expect(text).toContain('Tests: python3 -m pytest: 3 passed')
  expect(text).toContain(`Full log: /tmp/kiss-mini/${ID}/report.md`)
})

test('a hand-off with return off sends nothing back', async ($, on) => {
  const w = world(on)
  await handoff($, w, false)
  expect(w.sent.filter(m => !m.text.startsWith('KISS-MINI task'))).toEqual([])
  expect(await status($)).toContain(`${ID} bug ready: add subtracts`)
})

async function watch($: any, w: ReturnType<typeof world>, target: string) {
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kiss:kiss-mini', args: `watch ${target}` })
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' })
}

test('a watched CI run that goes from running to passed moves from watching to done, with one toast', async ($, on) => {
  const w = world(on)
  await watch($, w, 'run 123')
  expect(await status($)).toContain(`${ID} watch watching: run 123`)
  expect(w.spawned).toEqual([])
  const toasts = w.toasts.length
  w.gh.run = 'completed success'
  await w.clock.advance(60_000)
  expect(await status($)).toContain(`${ID} watch done: run 123 - passed`)
  expect(w.toasts.length).toBe(toasts + 1)
})

test('with the clock run past 24 hours, an open watch ends as expired', { timeoutMs: 60_000 }, async ($, on) => {
  const w = world(on)
  await watch($, w, 'pr 12')
  // In steps the mocked clock takes: each holds fewer than its 10,000 waits.
  await w.clock.advance(12 * 3600_000)
  await w.clock.advance(12 * 3600_000)
  expect(await status($)).toContain(`${ID} watch watching`)
  await w.clock.advance(120_000)
  expect(await status($)).toContain(`${ID} watch done: pr 12 - expired`)
})

test('with no change the checks space out to every 10 minutes, and no model is asked', async ($, on) => {
  const w = world(on)
  await watch($, w, 'pr 12')
  await w.clock.advance(60 * 60_000)
  const gaps = w.ghAt.slice(1).map((at, i) => at - (w.ghAt[i] ?? 0))
  expect(gaps.slice(0, 2)).toEqual([60_000, 120_000])
  expect(gaps.slice(-2)).toEqual([600_000, 600_000])
  expect(w.models).toBe(0)
})

test('a watched test command that fails ends failed with its last lines', async ($, on) => {
  const w = world(on)
  await watch($, w, 'pytest -q --fail')
  await w.clock.advance(60_000)
  expect(await status($)).toContain(`${ID} watch failed: pytest -q --fail - exit 1: collected 3 · line a · FAILED test_add - assert -1 == 5`)
  expect(w.spawned).toEqual([])
})

/** A worker's tool calls as the host sees them: the progress tool and an ordinary tool, both answered beneath. */
function tools(on: On) {
  on('tool.call', () => ({ result: {}, text: 'ok' }) as never)
}
async function working($: any, w: ReturnType<typeof world>) {
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kiss:kiss-mini', args: 'fix add so it returns the sum --base main' })
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' })
  await $.turn.start({ agentId: 'w1', text: w.spawned[0]?.prompt ?? '', turnId: 't1' })
}

test('a working task\'s row shows its kind, title, state, step n of m and its last tool call', async ($, on) => {
  const w = world(on)
  tools(on)
  await working($, w)
  await $.tool.call({ tool: 'mcp__kiss__progress', step: 2, total: 5, agentId: 'w1' } as never)
  await $.tool.call({ tool: 'Read', file_path: '/tmp/wt/calc.py', agentId: 'w1' } as never)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    const text = JSON.stringify(await ui.drawn())
    for (const part of [`${ID} code working: fix add so it returns the sum`, 'step 2 of 5', 'Read /tmp/wt/calc.py']) expect(text).toContain(part)
    await ui.unmount()
  }
})

test('the status line asks the small model at most every 30 seconds, and only on a new tool call', async ($, on) => {
  const w = world(on)
  tools(on)
  await working($, w)
  await $.tool.call({ tool: 'Read', file_path: 'calc.py', agentId: 'w1' } as never)
  expect(w.models).toBe(1)
  await w.clock.advance(10_000)
  await $.tool.call({ tool: 'Grep', pattern: 'add', agentId: 'w1' } as never)
  expect(w.models).toBe(1)
  await w.clock.advance(20_000)
  expect(w.models).toBe(1)
  await $.tool.call({ tool: 'Edit', file_path: 'calc.py', agentId: 'w1' } as never)
  expect(w.models).toBe(2)
  // The status line is written after the tool result went back: let it land.
  await w.clock.settle()
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /reads calc\.py \(2\)/ })).toBeDefined()
  await ui.unmount()
})

test('a task waiting for the owner sorts above a working task, and the band opens the pane', async ($, on) => {
  const base = { kind: 'question', sender: 's1', cwd: '/repo', started: NOW, host: 's1' }
  const w = world(on, {
    store: {
      'kiss-mini/task/a-work': { ...base, id: 'a-work', title: 'working one', state: 'working' },
      'kiss-mini/task/b-wait': { ...base, id: 'b-wait', title: 'waiting one', state: 'waiting for you' },
    },
  })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const text = JSON.stringify(await ui.drawn())
  expect(text.indexOf('waiting one')).toBeLessThan(text.indexOf('working one'))
  await ui.unmount()
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'mini-open' })
  expect(w.opened).toContain('kiss-mini')
  await band.unmount()
  expect(w.sent).toEqual([])
})

test('a fourth harness code task waits while three run, and an owner task still starts', async ($, on) => {
  const running = (n: number) => ({
    id: `h${n}`, kind: 'code', title: `harness ${n}`, brief: 'Kind: code', return: true, sender: 'c1', cwd: '/repo',
    state: 'working', started: NOW, host: 's1', agentId: `x${n}`, base: 'run', branch: `mini/h${n}`, worktree: `/tmp/h${n}`,
  })
  const w = world(on, { store: { 'kiss-mini/task/h1': running(1), 'kiss-mini/task/h2': running(2), 'kiss-mini/task/h3': running(3) } })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.tool.call({ tool: 'mcp__kiss__handoff', kind: 'code', title: 'fourth', brief: 'Kind: code', base: 'run', return: true } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent.at(-1)?.text ?? '' } as never)
  expect(w.spawned).toEqual([])
  expect(await status($)).toContain(`${ID} code working: fourth`)
  await w.clock.advance(1_000)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'owner fix --base main' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent.at(-1)?.text ?? '' } as never)
  expect(w.spawned.length).toBe(1)
  expect(w.spawned[0]?.prompt).toContain('owner fix')
  // One harness worker ends: the waiting one starts.
  await $.turn.complete({ agentId: 'x1', reason: 'answer', answer: 'State: failed\nSummary: no.', durationMs: 1, isAborted: false, turnId: 'tx' } as never)
  expect(w.spawned.length).toBe(2)
  expect(w.spawned[1]?.prompt).toContain('fourth')
})

test('a worker\'s question puts its row in waiting for you with one toast; the owner\'s answer in the pane goes to that worker', async ($, on) => {
  const w = world(on)
  tools(on)
  await working($, w)
  const toasts = w.toasts.length
  await $.turn.complete({ agentId: 'w1', reason: 'answer', answer: 'State: waiting for you\nSummary: Should add() also take floats?\nBranch: none', durationMs: 1, isAborted: false, turnId: 't1' } as never)
  expect(await status($)).toContain(`${ID} code waiting for you: fix add so it returns the sum - Should add() also take floats?`)
  expect(w.toasts.length).toBe(toasts + 1)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.input({ key: `answer-${ID}`, text: 'yes, floats too' })
  await ui.unmount()
  const wake = w.sent.at(-1)?.text ?? ''
  expect(wake).toContain(`KISS-MINI answer ${ID}`)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: wake } as never)
  const toWorker = w.sent.at(-1)
  expect(toWorker?.to).toContain('w1')
  expect(toWorker?.text).toContain('yes, floats too')
  expect(await status($)).toContain(`${ID} code working`)
  // The same worker goes on and reports again.
  await $.turn.complete({ agentId: 'w1', reason: 'answer', answer: READY, durationMs: 1, isAborted: false, turnId: 't2' } as never)
  expect(await status($)).toContain(`${ID} code ready`)
})

test('a worker the engine lists as waiting shows as waiting for you, with a way to open the host session', async ($, on) => {
  const w = world(on)
  tools(on)
  await working($, w)
  w.agents = [{ id: 'w1', description: 'mini', type: 'kiss:kiss-worker', status: 'waiting' }]
  await w.clock.advance(5_000)
  expect(await status($)).toContain(`${ID} code waiting for you`)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /claude attach s1/ })).toBeDefined()
  await ui.unmount()
  w.agents = [{ id: 'w1', description: 'mini', type: 'kiss:kiss-worker', status: 'running' }]
  await w.clock.advance(5_000)
  expect(await status($)).toContain(`${ID} code working`)
})

test('/kiss-mini stop on a working task stops its worker and marks it failed as stopped', async ($, on) => {
  const w = world(on)
  const ran: string[] = []
  on('tool.call', ($, e) => (ran.push(String(e.tool)), { result: {}, text: 'ok' }) as never)
  await working($, w)
  const r = await $.command.run({ command: 'kiss:kiss-mini', args: `stop ${ID}` } as never)
  expect(r.text).toContain(ID)
  expect(w.spawned.length).toBe(1)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent.at(-1)?.text ?? '' } as never)
  expect(await status($)).toContain(`${ID} code failed: fix add so it returns the sum - stopped`)
  const denied = await $.tool.call({ tool: 'Read', file_path: 'calc.py', agentId: 'w1' } as never)
  expect(JSON.stringify(denied)).toContain('stopped')
  expect(ran).toEqual([])
  // Its last answer changes nothing.
  await $.turn.complete({ agentId: 'w1', reason: 'answer', answer: READY, durationMs: 1, isAborted: false, turnId: 't2' } as never)
  expect(await status($)).toContain(`${ID} code failed`)
})

test('a code task past 30 minutes is stopped as timed out', async ($, on) => {
  const w = world(on)
  tools(on)
  await working($, w)
  await w.clock.advance(29 * 60_000)
  expect(await status($)).toContain(`${ID} code working`)
  await w.clock.advance(2 * 60_000)
  expect(await status($)).toContain(`${ID} code failed: fix add so it returns the sum - timed out after 30 minutes`)
})

test('RACE: a stop that arrives while a worker tool call runs stays a stop', async ($, on) => {
  const w = world(on)
  let release: () => void = () => {}
  on('tool.call', () => new Promise(res => { release = () => res({ result: {}, text: 'ok' }) }) as never)
  await working($, w)
  const call = $.tool.call({ tool: 'Bash', command: 'python3 long.py', agentId: 'w1' } as never)
  await w.clock.settle()
  await $.command.run({ command: 'kiss:kiss-mini', args: `stop ${ID}` } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent.at(-1)?.text ?? '' } as never)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('failed')
  release()
  await call
  expect([w.store[`kiss-mini/task/${ID}`].state, w.store[`kiss-mini/task/${ID}`].stopped]).toEqual(['failed', true])
})

test('RACE: an answer to a permission wait is not lost when the task changes during a tool call (timeout)', async ($, on) => {
  const w = world(on)
  let release: () => void = () => {}
  on('tool.call', () => new Promise(res => { release = () => res({ result: {}, text: 'ok' }) }) as never)
  await working($, w)
  const call = $.tool.call({ tool: 'Bash', command: 'python3 long.py', agentId: 'w1' } as never)
  await w.clock.settle()
  await w.clock.advance(31 * 60_000)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('failed')
  release()
  await call
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('failed')
})

test('ORPHAN: a working owner task of a host that is gone does not hold the owner slot forever', async ($, on) => {
  const orphan = { id: 'old1', kind: 'code', title: 'old', sender: 's0', cwd: '/repo', state: 'working', started: NOW - 3600_000, claimed: NOW - 3600_000, host: 'dead-host', agentId: 'gone', base: 'main', branch: 'mini/old1', worktree: '/tmp/old1' }
  const queued = { id: 'new1', kind: 'code', title: 'new', sender: 's0', cwd: '/repo', state: 'working', started: NOW, base: 'main', branch: 'mini/new1', worktree: '/tmp/new1' }
  const w = world(on, { store: { 'kiss-mini/task/old1': orphan, 'kiss-mini/task/new1': queued } })
  w.session = 'h2'
  await $.session.start({ cwd: '/', surface: null, isInteractive: false } as never)
  await w.clock.advance(2 * 60_000)
  expect(w.store['kiss-mini/task/old1'].state).not.toBe('working')
  expect(w.spawned.length).toBe(1)
})

test('TIMEOUT: an owner answer after 31 minutes of waiting does not stop the worker at once', async ($, on) => {
  const w = world(on)
  tools(on)
  await working($, w)
  await $.turn.complete({ agentId: 'w1', reason: 'answer', answer: 'State: waiting for you\nSummary: floats too?\nBranch: none', durationMs: 1, isAborted: false, turnId: 't1' } as never)
  await w.clock.advance(31 * 60_000)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('waiting for you')
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: `KISS-MINI answer ${ID} ${w.store[`kiss-mini/task/${ID}`].key}\nyes` } as never)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('working')
  await w.clock.advance(61_000)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('working')
})

test('ANSWER: a model-written peer message (no plugin) is not taken as the owner answer', async ($, on) => {
  const w = world(on)
  tools(on)
  await working($, w)
  await $.turn.complete({ agentId: 'w1', reason: 'answer', answer: 'State: waiting for you\nSummary: may I also rewrite mul()?\nBranch: none', durationMs: 1, isAborted: false, turnId: 't1' } as never)
  await $.session.receive({ origin: { kind: 'peer' }, text: `KISS-MINI answer ${ID}\nyes, rewrite mul too` } as never)
  expect(w.sent.some(m => m.to === 'w1' || JSON.stringify(m.to).includes('w1'))).toBe(false)
})

test('a question leaves no worktree; the pane names the full text; no State line on a question is done', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'ask why?' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  await $.turn.start({ agentId: 'w1', text: w.spawned[0]?.prompt ?? '', turnId: 't1' })
  await $.turn.complete({ agentId: 'w1', reason: 'answer', answer: 'Because add subtracts.', durationMs: 1, isAborted: false, turnId: 't1' } as never)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('done')
  expect(git(w).some(line => line.includes('worktree'))).toBe(false)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /full text: \/tmp\/kiss-mini\/.*report\.md/ })).toBeDefined()
  await ui.unmount()
})

test('a host that cannot start fails the task with claude\'s words', async ($, on) => {
  const w = world(on, { delivered: false, fail: { claude: { stderr: 'Workspace not trusted.' } } })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  const r = await $.command.run({ command: 'kiss:kiss-mini', args: 'ask why?' } as never)
  expect(r.text).toContain('could not start a host: Workspace not trusted.')
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('failed')
})

test('a claude run that throws fails the task with its words: one task, the skill does not run, no later host runs it', async ($, on) => {
  const w = world(on, { delivered: false, hang: ['claude'] })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  const r = await $.command.run({ command: 'kiss:kiss-mini', args: 'ask what does calc.py do?' } as never)
  expect(r.text).toContain('could not start a host: ')
  expect(Object.keys(w.store).filter(k => k.startsWith('kiss-mini/task/'))).toEqual([`kiss-mini/task/${ID}`])
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('failed')
  expect(w.store[`kiss-mini/task/${ID}`].report).toMatch(/^could not start a host: ./)

  // A host that starts later finds no task to run.
  w.session = 'h2'
  await $.session.start({ cwd: '/', surface: null, isInteractive: false } as never)
  expect(w.spawned.length).toBe(0)
})

test('a harness task offers only Discard; merged into its base by the harness, it ends done and its worktree goes', async ($, on) => {
  const w = world(on)
  await handoff($, w, false)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  for (const key of ['merge', 'push', 'pr']) expect(await ui.find({ key: `${key}-${ID}` })).toBeUndefined()
  expect(await ui.find({ key: `discard-${ID}` })).toBeDefined()
  await ui.unmount()
  w.merged = true
  await w.clock.advance(60_000)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('done')
  expect(git(w)).toContain(`git -C /repo worktree remove --force ${WT}`)
})

test('a hand-off watch returns its end to the sender', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.tool.call({ tool: 'mcp__kiss__handoff', kind: 'watch', title: 'CI', brief: 'watch CI', target: 'run 123', return: true } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  w.gh.run = 'completed success'
  await w.clock.advance(60_000)
  const back = w.sent.filter(m => !m.text.startsWith('KISS-MINI'))
  expect(back.length).toBe(1)
  expect(back[0]?.text).toContain('State: done')
  expect(back[0]?.text).toContain('Summary: passed')
})

test('a Draft PR that fails at gh says the branch was pushed', async ($, on) => {
  const w = world(on, { fail: { gh: { stderr: 'HTTP 422' } } })
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `pr-${ID}` })
  expect(w.toasts.at(-1)).toContain('pushed; draft PR failed: HTTP 422')
  await ui.unmount()
})

test('the host denies a worker\'s GitHub write tools of an MCP server', async ($, on) => {
  const w = world(on)
  tools(on)
  await ready($, w)
  const r = await $.tool.call({ tool: 'mcp__github__create_pull_request', title: 'x', agentId: 'w1' } as never)
  expect(JSON.stringify(r)).toContain('writes to GitHub')
})

test('a question may not write a file, and its commands leave no Python or pytest cache', async ($, on) => {
  const w = world(on)
  const ran: string[] = []
  on('tool.call', ($, e) => (ran.push(String((e as { command?: string }).command ?? e.tool)), { result: {}, text: 'ok' }) as never)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'ask does pytest pass?' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  await $.turn.start({ agentId: 'w1', text: w.spawned[0]?.prompt ?? '', turnId: 't1' })
  const r = await $.tool.call({ tool: 'Write', file_path: '/repo/x.py', content: 'x', agentId: 'w1' } as never)
  expect(JSON.stringify(r)).toContain('changes no file')
  expect(JSON.stringify(r)).not.toContain('only in its worktree')
  await $.tool.call({ tool: 'Bash', command: 'pytest -q', agentId: 'w1' } as never)
  // The worktree guard leaves a question alone: its command runs in its checkout.
  await $.tool.call({ tool: 'Bash', command: 'git -C /repo commit -m x', agentId: 'w1' } as never)
  const quiet = `export PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS="-p no:cacheprovider"; cd '/repo' && `
  // The brief names the whole prefix; a command that holds it is left as it is.
  expect(w.spawned[0]?.prompt).toContain(`\nBash: ${quiet.replace("'/repo'", "'<Checkout>'")}<command>\n`)
  await $.tool.call({ tool: 'Bash', command: `${quiet}ls`, agentId: 'w1' } as never)
  expect(ran).toEqual([`${quiet}pytest -q`, `${quiet}git -C /repo commit -m x`, `${quiet}ls`])
})

test('a ready task with no commit is not taken as merged', async ($, on) => {
  const w = world(on)
  w.ahead = 0
  await ready($, w)
  w.merged = true
  await w.clock.advance(60_000)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('ready')
  expect(git(w).some(line => line.includes('worktree remove'))).toBe(false)
})

test('a merged task whose worktree has uncommitted changes ends done and keeps the worktree, with a toast', async ($, on) => {
  const w = world(on)
  await ready($, w)
  w.merged = true
  w.dirty = ' M calc.py\n'
  await w.clock.advance(60_000)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('done')
  expect(w.store[`kiss-mini/task/${ID}`].worktree).toBe(WT)
  expect(git(w).some(line => line.includes('worktree remove'))).toBe(false)
  expect(w.toasts.at(-1)).toContain(`uncommitted changes: ${WT}`)
})

test('the live host takes over a ready task of a gone host, so its merge is seen', async ($, on) => {
  const t = { id: 'r1', kind: 'code', title: 'r', sender: 's0', cwd: '/repo', state: 'ready', started: NOW, host: 'gone', agentId: 'x', base: 'main', branch: 'mini/r1', worktree: '/tmp/r1', ahead: 1 }
  const w = world(on, { store: { 'kiss-mini/task/r1': t } })
  w.merged = true
  await $.session.start({ cwd: '/', surface: null, isInteractive: false } as never)
  await w.clock.advance(60_000)
  expect(w.store['kiss-mini/task/r1'].state).toBe('done')
})

test('an aborted turn with no answer is no report: the task waits for the orphan check', async ($, on) => {
  const w = world(on)
  tools(on)
  await working($, w)
  await $.turn.complete({ agentId: 'w1', reason: 'aborted', answer: '', durationMs: 1, isAborted: true, turnId: 't9' } as never)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('working')
})

test('a host whose beat is over 3 minutes old is not sent to: a new host starts', async ($, on) => {
  const w = world(on, { store: { 'kiss-mini/host': { sessionId: 'old', beat: NOW - 4 * 60_000 } } })
  w.session = 's9'
  const r = await $.command.run({ command: 'kiss:kiss-mini', args: 'ask why?' } as never)
  expect(w.sent).toEqual([])
  expect(r.text).toContain('started a new host')
})

test('/kiss-mini --now skips the three checks; a plain /kiss-mini runs them', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: '--now fix it --base main' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent.at(-1)?.text ?? '' } as never)
  expect(w.spawned[0]?.prompt).toContain('Checks: skip (owner)')
  expect(w.spawned[0]?.prompt).toContain('# Mini task 1102-143005: fix it')
  await w.clock.advance(1_000)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'ask why?' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent.at(-1)?.text ?? '' } as never)
  expect(w.spawned[1]?.prompt).toContain('Checks: run')
})

test('with real-length paths a 400-character task keeps its first 200 characters in a brief of at most 1,500', async ($, on) => {
  const tmp = '/var/folders/x_/abcdefghijklmnopqrstuvwxyz01/T/'
  const cwd = pin('/home/someone/.cache/agent-501/-home-someone-Projects-Repo-SOMEAPP-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d/scratchpad/run1/repo-with-a-long-name')
  const w = world(on, { tmp, cwd })
  const text = `fix ${'the parser drops the last field '.repeat(12)}`.trim().slice(0, 400)
  await $.session.start({ cwd, surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: `${text} --base main` } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  const prompt = w.spawned[0]?.prompt ?? ''
  expect(prompt.length).toBeLessThanOrEqual(1500)
  expect(prompt).toContain(text.slice(0, 200))
})

test('when the paths leave under 200 characters for the task text, its first 200 characters still stay', async ($, on) => {
  const deep = '/very-long-folder-name-for-a-test-0123456789'.repeat(6)
  const w = world(on, { tmp: `/tmp${deep}/`, cwd: `/home/someone${deep}/repo` })
  const text = `fix ${'the parser drops the last field '.repeat(12)}`.trim().slice(0, 400)
  await $.session.start({ cwd: `/home/someone${deep}/repo`, surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: `${text} --base main` } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  expect(w.spawned[0]?.prompt).toContain(text.slice(0, 200))
  expect(w.spawned[0]?.prompt).not.toContain(text.slice(0, 201))
})

test('in an indexed repo a code task\'s brief names W, the CodeGraph commands with -p and the seed file, within 1,500 characters', async ($, on) => {
  // A long cwd, so pin() has room to shorten it for a long checkout path; Linux's /tmp/ keeps the brief's budget. The
  // brief's task text keeps exactly its 200 characters here: the path is 33 characters shorter since the Bash line (D24).
  const tmp = '/tmp/'
  const cwd = pin('/home/someone/.cache/agent-501/-home-someone-Projects-Repo-SOMEAPP-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d/scratchpad/run1/notes-app-with-a-long-name-0123456789abcdefghijklmn')
  const w = world(on, { tmp, cwd, indexed: true })
  await $.session.start({ cwd, surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: `fix ${'the long bug text '.repeat(30)}`.trim() } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  const dir = `/tmp/kiss-mini/${ID}`
  const prompt = w.spawned[0]?.prompt ?? ''
  expect(prompt.length).toBeLessThanOrEqual(1500)
  expect(prompt).toContain(`Worktree: ${dir}/wt\nTask folder: ${dir}\n`)
  expect(prompt).toContain('CodeGraph (never cd first): codegraph explore|node|callers -p "$PWD" <names>; codegraph sync -q "$PWD" after edits; seed: seed.md in the Task folder')
  // The worker starts in W, so "$PWD" in the line is W.
  expect(w.spawned[0]?.cwd).toBe(`${dir}/wt`)
  expect(w.files[`${dir}/seed.md`]).toBe('SEED: calc.py add()\n')
  // The new worktree gets its own index before the seed reads it.
  const cg = w.runs.filter(a => a[0] === 'codegraph').map(a => a.slice(0, 4).join(' '))
  expect(cg).toEqual([`codegraph status ${cwd}`, `codegraph init -y ${dir}/wt`, `codegraph explore -p ${dir}/wt`])
})

test('a code task\'s brief names ponytail first, as handoff.md\'s skill rows do', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'fix add so it returns the sum --base main' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  expect(w.spawned[0]?.prompt).toContain(
    'Suggested skills: ponytail first, tdd, CodeGraph; pr for the pull request body')
})

test('a repo with no index gets no seed and no CodeGraph line; the task still starts', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'fix add so it returns the sum --base main' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  // the CodeGraph command line, not the word: the plugin's own path may hold "codegraph"
  expect(w.spawned[0]?.prompt).not.toMatch(/^CodeGraph |codegraph (explore|node|callers|sync)\b/m)
  expect(Object.keys(w.files).some(f => f.endsWith('seed.md'))).toBe(false)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('working')
})

test('with no codegraph on the machine the task starts with no seed and no error', async ($, on) => {
  const w = world(on, { hang: ['codegraph'] })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'fix add so it returns the sum --base main' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  expect(w.spawned).toHaveLength(1)
  expect(Object.keys(w.files).some(f => f.endsWith('seed.md'))).toBe(false)
  expect(w.store[`kiss-mini/task/${ID}`].state).toBe('working')
})

test('a question whose worker returns no answer ends failed: the worker returned no answer', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'ask why?' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  await $.turn.start({ agentId: 'w1', text: w.spawned[0]?.prompt ?? '', turnId: 't1' })
  await $.turn.complete({ agentId: 'w1', reason: 'answer', answer: ' \n', durationMs: 1, isAborted: false, turnId: 't1' } as never)
  expect([w.store[`kiss-mini/task/${ID}`].state, w.store[`kiss-mini/task/${ID}`].report]).toEqual(['failed', 'the worker returned no answer'])
})

test('a slow seed does not count toward the 30 minutes of a code task', async ($, on) => {
  const w = world(on, { indexed: true, seedMs: 20 * 60_000 })
  tools(on)
  await working($, w)
  await w.clock.advance(15 * 60_000)
  expect(await status($)).toContain(`${ID} code working`)
  await w.clock.advance(16 * 60_000)
  expect(await status($)).toContain(`${ID} code failed: fix add so it returns the sum - timed out after 30 minutes`)
})

test('a merged task whose worktree holds only the new .codegraph/ index ends done and its worktree goes', async ($, on) => {
  const w = world(on)
  await ready($, w)
  w.merged = true
  w.dirty = '?? .codegraph/\n'
  await w.clock.advance(60_000)
  expect(git(w)).toContain(`git -C /repo worktree remove --force ${WT}`)
  expect([w.store[`kiss-mini/task/${ID}`].state, w.store[`kiss-mini/task/${ID}`].worktree]).toEqual(['done', undefined])
})

test('a task started in a subfolder of an indexed repo still gets its seed', async ($, on) => {
  const w = world(on, { cwd: '/repo/pkg', top: '/repo', indexed: true })
  await $.session.start({ cwd: '/repo/pkg', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'kiss:kiss-mini', args: 'fix add so it returns the sum --base main' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  expect(w.files[`/tmp/kiss-mini/${ID}/seed.md`]).toBe('SEED: calc.py add()\n')
})
