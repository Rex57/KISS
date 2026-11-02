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
type Opts = { delivered?: boolean; branch?: string; fail?: Record<string, { stdout?: string; stderr?: string }>; store?: Record<string, unknown> }
function world(on: On, { delivered = true, branch = 'main', fail = {}, store }: Opts = {}) {
  const w = {
    session: 's1',
    branch,
    sent: [] as { to: string; text: string }[],
    spawned: [] as { prompt: string; subagentType?: string; cwd?: string }[],
    runs: [] as string[][],
    toasts: [] as string[],
    files: {} as Record<string, string>,
  }
  mock.clock(on, { now: NOW })
  mock.store(on, store)
  mock.env(on, { KISS_MINI_HOST: '1', TMPDIR: '/tmp/' })
  on('session.id', () => ({ value: w.session }))
  on('session.cwd', () => ({ value: '/repo' }))
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
    // The checkout is on w.branch; the worker's branch differs from the base by one line; `fail` names git verbs that fail.
    const bad = fail[e.argv[3] ?? ''] ?? fail[e.argv[0] ?? '']
    if (bad) return { value: { exitCode: 1, stdout: bad.stdout ?? '', stderr: bad.stderr ?? '', isStdoutTruncated: false, isStderrTruncated: false } }
    const out = e.argv.includes('--abbrev-ref') ? `${w.branch}\n` : e.argv.includes('--shortstat') ? ' 1 file changed, 1 insertion(+), 1 deletion(-)\n' : ''
    return { value: { exitCode: 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.open', () => ({ value: { isPlaced: true } }) as never)
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
  for (const command of [`git push -u origin mini/${ID}`, 'git -C /repo merge main', 'gh pr create --draft', 'cd x && git push']) {
    const r = await $.tool.call({ tool: 'Bash', command, agentId: 'w1' } as never)
    expect(JSON.stringify(r)).toContain('press in the /mini pane')
  }
  await $.tool.call({ tool: 'Bash', command: 'git commit -m fix', agentId: 'w1' } as never)
  await $.tool.call({ tool: 'Bash', command: 'git push', agentId: 'other' } as never)
  expect(ran).toEqual(['git commit -m fix', 'git push'])
})

test('a delivered task keeps no PR body, diff or tests', async ($, on) => {
  const w = world(on)
  await ready($, w)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: `push-${ID}` })
  expect(await ui.find({ type: 'Text', text: /tests:/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /1 file changed/ })).toBeUndefined()
  await ui.unmount()
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
