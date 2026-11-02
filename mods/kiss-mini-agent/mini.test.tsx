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
  /** argv[0] values whose run rejects, as a timed-out or missing command does. */
  hang?: string[]
  tmp?: string
  cwd?: string
}
function world(on: On, { delivered = true, branch = 'main', fail = {}, store, hang = [], tmp = '/tmp/', cwd = '/repo' }: Opts = {}) {
  const w = {
    session: 's1',
    branch,
    /** A merge under way in the checkout (MERGE_HEAD): the owner's own, or a failed merge's. */
    merging: false,
    store: {} as Record<string, any>,
    sent: [] as { to: string; text: string }[],
    spawned: [] as { prompt: string; subagentType?: string; cwd?: string }[],
    runs: [] as string[][],
    toasts: [] as string[],
    files: {} as Record<string, string>,
  }
  mock.clock(on, { now: NOW })
  // The store in memory, readable by the test: the ledger is the contract every session reads.
  const mem: Record<string, unknown> = JSON.parse(JSON.stringify(store ?? {}))
  w.store = mem
  on('store.get', ($, e) => ({ value: mem[e.key] }) as never)
  on('store.set', ($, e) => ((mem[e.key] = JSON.parse(JSON.stringify(e.value))), { value: undefined }) as never)
  on('store.delete', ($, e) => (delete mem[e.key], { value: undefined }) as never)
  on('store.keys', () => ({ value: Object.keys(mem) }) as never)
  mock.env(on, { KISS_MINI_HOST: '1', TMPDIR: tmp })
  on('session.id', () => ({ value: w.session }))
  on('session.cwd', () => ({ value: cwd }))
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('command.register', ($, e) => ({ value: { command: e.name } }) as never)
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
  on('process.run', ($, e) => {
    w.runs.push([...e.argv])
    if (hang.includes(e.argv[0] ?? '')) throw new Error(`${e.argv[0]}: timed out after 120000 ms`)
    if (e.argv.includes('MERGE_HEAD')) return { value: { exitCode: w.merging ? 0 : 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv.includes('--abort')) w.merging = false
    // The checkout is on w.branch; the worker's branch differs from the base by one line; `fail` names git verbs that fail.
    const bad = fail[`${e.argv[3]} ${e.argv[4]}`] ?? fail[e.argv[3] ?? ''] ?? fail[e.argv[0] ?? '']
    if (bad && e.argv[3] === 'merge') w.merging = true
    if (bad) return { value: { exitCode: 1, stdout: bad.stdout ?? '', stderr: bad.stderr ?? '', isStdoutTruncated: false, isStderrTruncated: false } }
    const out = e.argv.includes('--abbrev-ref') ? `${w.branch}\n` : e.argv.includes('--shortstat') ? ' 1 file changed, 1 insertion(+), 1 deletion(-)\n' : ''
    return { value: { exitCode: 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.open', () => ({ value: { isPlaced: true } }) as never)
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

const status = async ($: any) => (await $.command.run({ command: 'mini', args: 'status' })).text as string

test('/mini ask records a working task and the band reads 1 working; the report makes it done with one toast', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'mini', args: 'ask what does tickets.py check?' } as never)
  expect(await status($)).toContain(`${ID} question working: what does tickets.py check?`)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /working/ }))?.text).toBe('mini: 1 working')

  // The host takes the task in code: the message is consumed, a kiss-worker starts in the sender's folder.
  expect(w.sent.length).toBe(1)
  expect(w.sent[0]?.text).toContain(`KISS-MINI task ${ID}`)
  const got = await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  expect(got.consumed).toBeDefined()
  expect(w.spawned.length).toBe(1)
  expect(w.spawned[0]?.subagentType).toBe('kiss:kiss-worker')
  expect(w.spawned[0]?.cwd).toBe('/repo')
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

test('when the send to the host is refused, the mod starts a new host and the task still goes in', async ($, on) => {
  const w = world(on, { delivered: false })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'mini', args: 'ask why?' } as never)
  expect(w.spawned.length).toBe(0)
  const start = w.runs.find(argv => argv.includes('--bg'))
  expect(start?.slice(0, 4)).toEqual(['claude', '--bg', '--name', 'kiss-mini-agent'])
  expect(start).toContain(JSON.stringify({ env: { KISS_MINI_HOST: '1' } }))

  // The new host session starts: it takes the task that waits in the ledger.
  w.session = 'h2'
  await $.session.start({ cwd: '/', surface: null, isInteractive: false } as never)
  expect(w.spawned.length).toBe(1)
  expect(w.spawned[0]?.prompt).toContain('why?')
})

test('with no open task the band draws nothing', async ($, on) => {
  world(on)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ type: 'Text', text: /prompt only/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /mini:/ })).toBeUndefined()
    await ui.unmount()
  }
})

const PANE = {
  plugin: 'kiss',
  component: 'Pane',
  requestId: 'kiss-mini',
  props: { title: 'mini', isFocused: true, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 20 }, view: {} },
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
  await $.command.run({ command: 'mini', args: 'fix add so it returns the sum --base main' })
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
  await $.command.run({ command: 'mini', args: 'status bar is red, fix it' } as never)
  await $.session.receive({ origin: { kind: 'peer', plugin: 'kiss' }, text: w.sent[0]?.text ?? '' } as never)
  expect(git(w)).toContain(`git -C /repo worktree add -b mini/${ID} ${WT} dev`)
  expect(await status($)).toContain(`${ID} code working: status bar is red, fix it`)
})

test('from a detached HEAD, with no --base, the code task is refused and says why', async ($, on) => {
  const w = world(on, { branch: 'HEAD' })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  const r = await $.command.run({ command: 'mini', args: 'fix it' } as never)
  expect(r.text).toContain('--base')
  expect(w.sent).toEqual([])
  expect(await status($)).toBe('mini: no tasks.')
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
  await $.command.run({ command: 'mini', args: text } as never)
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
    'git --no-pager push origin x', 'git -C/x push', 'gh api -X POST repos/o/r/pulls -f head=x -f base=main']) {
    const r = await $.tool.call({ tool: 'Bash', command, agentId: 'w1' } as never)
    expect(JSON.stringify(r)).toContain('press in the /mini pane')
  }
  const allowed = ['git commit -m "docs: how to git push a branch"', 'git commit -m fix', 'git add merge.py', 'git commit -m "merge the push docs"', 'git merge-base main HEAD', 'git log --grep merge', 'gh pr view 12']
  for (const command of allowed) await $.tool.call({ tool: 'Bash', command, agentId: 'w1' } as never)
  await $.tool.call({ tool: 'Bash', command: 'git push', agentId: 'other' } as never)
  expect(ran).toEqual([...allowed, 'git push'])
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
  expect(w.toasts.at(-1)).toContain(`mini ${ID}: pr failed`)
  expect(w.store[`kiss-mini/task/${ID}`].busy).toBeUndefined()
  expect(await ui.find({ key: `pr-${ID}` })).toBeDefined()
  expect(await ui.find({ key: `discard-${ID}` })).toBeDefined()
  await ui.unmount()
})

test('a failed worktree add leaves no worktree to Discard, and the task ends with a time', async ($, on) => {
  const w = world(on, { fail: { worktree: { stderr: "fatal: invalid reference: nosuch" } } })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'mini', args: 'fix it --base nosuch' } as never)
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
  const cwd = '/home/someone/.cache/agent-501/-home-someone-Projects-Repo-SOMEAPP-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d/scratchpad/run1/repo'
  const w = world(on, { tmp, cwd })
  await $.session.start({ cwd, surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'mini', args: `fix ${'the long bug text '.repeat(30)}`.trim() } as never)
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
