// kiss-mini-agent: /mini in every session, one background host session that runs the workers in code.
// The ledger is `$.store` (shared by every session on the machine): one key per task, one for the host.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Delivery, State, Task } from './types'

type $ = EngineInterface

const TASK = 'kiss-mini/task/'
const HOST = 'kiss-mini/host'
const HOST_NAME = 'kiss-mini-agent'
const OPEN: State[] = ['waiting for you', 'working', 'ready', 'watching']
const TOAST: State[] = ['done', 'ready', 'waiting for you', 'failed']
const ENDED: State[] = ['done', 'failed']
const SUMMARY_MAX = 600
const PANE = 'kiss-mini'
const KEEP_MS = 7 * 24 * 3600_000
const SHOW_ENDED = 10

// The band draws from this copy of the ledger; a timer refreshes it, as other sessions write the store.
const ledger = atom({ plugin: 'kiss', key: 'mini' } as const, [], { shape: 'mini-1' })

const isHost = async ($: $) => (await $.env.get('KISS_MINI_HOST')) === '1'
const save = ($: $, t: Task) => $.store.set(TASK + t.id, t)

async function tasks($: $): Promise<Task[]> {
  const keys = (await $.store.keys()).filter(k => k.startsWith(TASK))
  return (await Promise.all(keys.map(k => $.store.get(k)))) as Task[]
}

async function folder($: $, id: string) {
  const tmp = (await $.env.get('TMPDIR')) || '/tmp/'
  return `${tmp.replace(/\/$/, '')}/kiss-mini/${id}`
}

/** The worker's report: its State line and its Summary (up to the next field), cut to 600 characters. */
export function parseReport(answer: string): { state: State; summary: string } {
  const state = /^State:\s*(ready|done|failed|waiting for you)\b/im.exec(answer)?.[1]?.toLowerCase() as State | undefined
  const summary = /^Summary:\s*([\s\S]*?)(?=^\w[\w ]*:|\n\n|$(?![\s\S]))/im.exec(answer)?.[1]?.trim() ?? answer.trim()
  return { state: state ?? 'failed', summary: summary.slice(0, SUMMARY_MAX) }
}

const BRIEF_MAX = 1500
// A command that pushes, merges or opens a pull request: git's subcommand (after -C/-c options), or gh pr create|merge|ready.
const DELIVERS = /\bgit(?:\s+-[Cc]\s+\S+)*\s+(?:push|merge)(?=\s|$|[;&|)])|\bgh\s+pr\s+(?:create|merge|ready)\b/
const NOT_GIVEN = 'not given: read the files the first line names.'

function briefLines(t: Task, title: string, rules: string, dir: string) {
  const head = [`# Mini task ${t.id}: ${title}`, `Kind: ${t.kind}`]
  const tail = ['Return: owner    Owner order: yes', `Rules: ${rules}`]
  if (t.kind === 'question') {
    return [...head, `Checkout: ${t.cwd}    Task folder: ${dir}`, ...tail,
      "Summary: answer the owner's question in the first line.",
      `Current behaviour: ${NOT_GIVEN}`,
      'Expected behaviour: an answer, with no change to any file.',
      `Key interfaces: ${NOT_GIVEN}`,
      'Acceptance checks:',
      '- The answer names the files and lines it rests on.',
      'Out of scope: any change to a file.',
      'Suggested skills: research',
    ].join('\n')
  }
  return [...head, `Checkout: ${t.cwd}    Base: ${t.base}    Branch: ${t.branch}    Worktree: ${t.worktree}`, `Task folder: ${dir}`, ...tail,
    'Summary: the change the first line asks for.',
    `Current behaviour: ${NOT_GIVEN}`,
    'Expected behaviour: as the first line says.',
    `Key interfaces: ${NOT_GIVEN}`,
    'Acceptance checks:',
    "- A test or a command shows the change works; the project's tests pass.",
    `- One commit on ${t.branch}; nothing pushed or merged.`,
    '- The full text ends with a "## Pull request body" section.',
    'Out of scope: anything the first line does not ask for.',
    'Suggested skills: tdd, ponytail, CodeGraph; pr for the pull request body',
  ].join('\n')
}

/** The brief in handoff.md's format, at most 1,500 characters: a task text that does not fit is cut, its whole text is in the task folder. */
function brief(t: Task, rules: string, dir: string): { text: string; isCut: boolean } {
  const whole = briefLines(t, t.title, rules, dir)
  if (whole.length <= BRIEF_MAX) return { text: whole, isCut: false }
  const more = `... (whole text: ${dir}/task.md)`
  const room = BRIEF_MAX - briefLines(t, '', rules, dir).length - more.length
  return { text: briefLines(t, t.title.slice(0, Math.max(0, room)) + more, rules, dir), isCut: true }
}

/** Copies the ledger into the band's state and toasts each of this session's tasks that reached a state for the owner. */
async function refresh($: $) {
  const list = await tasks($)
  await update($, ledger, () => list)
  const me = await $.session.id()
  for (const t of list) {
    if (t.sender !== me || t.notified || !TOAST.includes(t.state)) continue
    await save($, { ...t, notified: true })
    $.ui.toast(`mini ${t.id} ${t.state}: ${t.title}`)
  }
}

/** Host: the ledger forgets ended tasks after 7 days; one that still holds a worktree waits for its Discard. */
async function prune($: $) {
  const now = await $.clock.now()
  for (const t of await tasks($)) {
    if (ENDED.includes(t.state) && !t.worktree && (t.finished ?? t.started) < now - KEEP_MS) await $.store.delete(TASK + t.id)
  }
}

/** Host: claims the task, then starts its worker; a task another host claimed is left alone. */
async function run($: $, id: string) {
  const t = (await $.store.get(TASK + id)) as Task | undefined
  if (!t || t.host || t.state !== 'working') return
  await save($, { ...t, host: await $.session.id() })
  if (t.kind === 'code') {
    const made = await $.process.run(['git', '-C', t.cwd, 'worktree', 'add', '-b', t.branch!, t.worktree!, t.base!])
    // No worktree was made: nothing is left to Discard.
    if (made.exitCode !== 0) {
      return save($, { ...t, state: 'failed', report: made.stderr.trim().slice(0, SUMMARY_MAX), worktree: undefined, branch: undefined, finished: await $.clock.now() })
    }
  }
  const rules = `${$.plugin.root}/skills/kiss-mini-agent/references/handoff.md`
  const dir = await folder($, id)
  const b = brief(t, rules, dir)
  if (b.isCut) await $.fs.write(`${dir}/task.md`, t.title)
  const r = await $.agent.spawn({
    subagentType: 'kiss:kiss-worker',
    prompt: b.text,
    description: `mini ${id}: ${t.title.slice(0, 80)}`,
    cwd: t.worktree ?? t.cwd,
  })
  // The worker's turn.start may have written the task meanwhile: build on the stored entry.
  const now = (await $.store.get(TASK + id)) as Task
  if (r.deny !== undefined) await save($, { ...now, state: 'failed', report: r.deny, finished: await $.clock.now() })
  else if (r.agentId) await save($, { ...now, agentId: r.agentId })
}

/** Sender: wakes the host; when no host takes the message, starts one (it takes every waiting task as it starts). */
async function send($: $, id: string) {
  const host = (await $.store.get(HOST)) as { sessionId: string } | undefined
  if (host && (await $.session.send({ to: { sessionId: host.sessionId }, text: `KISS-MINI task ${id}` })).isDelivered) return 'sent'
  // No prompt: the host's own model never runs. Haiku in case the person attaches and types.
  await $.process.run(['claude', '--bg', '--name', HOST_NAME, '--model', 'haiku', '--plugin-dir', $.plugin.root], {
    env: { KISS_MINI_HOST: '1' },
  })
  return 'started a new host'
}

const DELIVERY: [Delivery, string][] = [['merge', 'Merge into the base'], ['push', 'Push'], ['pr', 'Draft PR'], ['discard', 'Discard']]

/** Whether the pane offers this delivery: Discard for any code task that still has a worktree, the others when ready. */
const offers = (t: Task, how: Delivery) =>
  t.kind === 'code' && !t.busy && (how === 'discard' ? !!t.worktree && t.state !== 'working' : t.state === 'ready')

/** Owner only: called from a press in the pane, never from a message or a tool. Nothing else merges, pushes or opens a PR. */
// Presses in this session that are under way: the store's claim covers other sessions, this covers the read before it.
const pressed = new Set<string>()

async function deliver($: $, id: string, how: Delivery) {
  if (pressed.has(id)) return
  pressed.add(id)
  try {
    await deliverOnce($, id, how)
  } finally {
    pressed.delete(id)
  }
}

async function deliverOnce($: $, id: string, how: Delivery) {
  const t = (await $.store.get(TASK + id)) as Task | undefined
  if (!t || !offers(t, how) || !t.branch || !t.worktree) return
  await save($, { ...t, busy: how })
  const failed = async (words: string) => {
    await save($, t)
    await refresh($)
    $.ui.toast(`mini ${id}: ${how} failed: ${words.trim().replace(/\s*\n\s*/g, ' · ').slice(0, 400)}`)
  }
  try {
    const git = (...args: string[]) => $.process.run(['git', '-C', t.cwd, ...args], { timeoutMs: 120_000 })
    let r = { exitCode: 0, stdout: '', stderr: '' }
    if (how === 'merge') {
      const head = (await git('rev-parse', '--abbrev-ref', 'HEAD')).stdout.trim()
      const merging = (await git('rev-parse', '-q', '--verify', 'MERGE_HEAD')).exitCode === 0
      const unmerged = (await git('diff', '--name-only', '--diff-filter=U')).stdout.trim()
      if (head !== t.base) r = { exitCode: 1, stdout: '', stderr: `check out ${t.base} in ${t.cwd} first` }
      else if (merging || unmerged) r = { exitCode: 1, stdout: '', stderr: `${t.cwd} has a merge of its own under way: finish or abort it first` }
      // No merge was under way before this one, so a MERGE_HEAD now is this press's own.
      else if ((r = await git('merge', '--no-edit', t.branch)).exitCode !== 0 && (await git('rev-parse', '-q', '--verify', 'MERGE_HEAD')).exitCode === 0) {
        await git('merge', '--abort')
      }
    } else if (how !== 'discard') {
      r = await git('push', '-u', 'origin', t.branch)
      if (r.exitCode === 0 && how === 'pr') {
        r = await $.process.run(['gh', 'pr', 'create', '--draft', '--base', t.base!, '--head', t.branch, '--title', t.title, '--body', t.pr ?? t.report ?? ''], { cwd: t.cwd, timeoutMs: 120_000 })
      }
    }
    if (r.exitCode !== 0) return failed(`${r.stdout}\n${r.stderr}`)
    // The delivered work is the branch (or, for a discard, nothing): the worktree goes, whatever it holds.
    const gone = await git('worktree', 'remove', '--force', t.worktree)
    if (how === 'discard') await git('branch', '-D', t.branch)
    if (gone.exitCode !== 0) $.ui.toast(`mini ${id}: worktree kept at ${t.worktree}: ${gone.stderr.trim().replace(/\s*\n\s*/g, ' · ').slice(0, 200)}`)
    const { pr, diff, tests, ...rest } = t
    await save($, { ...rest, state: 'done', delivered: how, ...(gone.exitCode === 0 ? { worktree: undefined } : {}) })
    await refresh($)
  } catch (err) {
    await failed(String(err))
  }
}

async function newId($: $) {
  const d = new Date(await $.clock.now()).toISOString()
  const base = `${d.slice(5, 7)}${d.slice(8, 10)}-${d.slice(11, 13)}${d.slice(14, 16)}${d.slice(17, 19)}`
  let id = base
  for (let n = 2; await $.store.get(TASK + id); n++) id = `${base}-${n}`
  return id
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'mini',
      description: 'kiss-mini-agent: /mini <task> a code change, /mini ask <question>, /mini status (alone) the list; no argument opens the pane',
      argumentHint: '<task> [--base <branch>] | ask <question> | status',
    })
    if (await isHost($)) {
      await $.store.set(HOST, { sessionId: await $.session.id(), beat: await $.clock.now() })
      await prune($)
      $.clock.every(60_000, async () => {
        await $.store.set(HOST, { sessionId: await $.session.id(), beat: await $.clock.now() })
        await prune($)
      })
      for (const t of await tasks($)) if (t.state === 'working' && !t.host) await run($, t.id)
    }
    $.clock.every(5_000, () => refresh($))
    await refresh($)
    return next(e)
  })

  on('command.run', { command: 'mini' }, async ($, e) => {
    const [verb = '', ...rest] = e.args.trim().split(/\s+/).filter(Boolean)
    if (verb === '') {
      await $.ui.open({ id: PANE, title: 'mini' })
      return { text: 'mini: pane opened.' }
    }
    if (e.args.trim() !== 'status') {
      const id = await newId($)
      const cwd = await $.session.cwd()
      const t: Task = { id, kind: 'question', title: rest.join(' '), sender: await $.session.id(), cwd, state: 'working', started: await $.clock.now() }
      if (verb !== 'ask') {
        const words = [verb, ...rest]
        const at = words.indexOf('--base')
        const base = at >= 0 ? words.splice(at, 2)[1] : undefined
        const head = base ?? (await $.process.run(['git', '-C', cwd, 'rev-parse', '--abbrev-ref', 'HEAD'])).stdout.trim()
        if (!head || head === 'HEAD') return { text: `mini: ${cwd} is on no branch (or in no repository): name one with --base <branch>.` }
        Object.assign(t, { kind: 'code', title: words.join(' '), base: head, branch: `mini/${id}`, worktree: `${await folder($, id)}/wt` })
      }
      if (!t.title) return { text: 'mini: say what to do: /mini <task>, /mini ask <question>.' }
      await save($, t)
      await refresh($)
      return { text: `mini ${id}: ${t.kind} started (${await send($, id)}).` }
    }
    const lines = (await tasks($)).map(t => `${t.id} ${t.kind} ${t.state}: ${t.title}${t.report ? ` - ${t.report}` : ''}`)
    return { text: lines.join('\n') || 'mini: no tasks.' }
  })

  // Host: a task message is taken in code, so the host's own model makes no turn for it.
  on('session.receive', async ($, e, next) => {
    const id = /KISS-MINI task (\S+)/.exec(e.text)?.[1]
    if (!id || !(await isHost($))) return next(e)
    await run($, id)
    return { consumed: `kiss-mini-agent task ${id}` }
  })

  // Host: a worker's first turn names its task in its brief's first line; from then on its agentId does.
  on('turn.start', async ($, e, next) => {
    const id = e.agentId && (await isHost($)) ? /^# Mini task (\S+):/.exec(e.text)?.[1] : undefined
    const t = id && ((await $.store.get(TASK + id)) as Task | undefined)
    if (t) await save($, { ...t, agentId: e.agentId })
    return next(e)
  })

  // Host: a worker's report ends its task in the ledger; the full text goes to the task folder.
  on('turn.complete', async ($, e, next) => {
    if (e.agentId === undefined || !(await isHost($))) return next(e)
    const t = (await tasks($)).find(x => x.agentId === e.agentId)
    if (!t) return next(e)
    const { state, summary } = parseReport(e.answer)
    const log = `${await folder($, t.id)}/report.md`
    await $.fs.write(log, e.answer)
    const done: Task = { ...t, state, report: summary, log, finished: await $.clock.now() }
    if (t.kind === 'code') {
      const stat = await $.process.run(['git', '-C', t.cwd, 'diff', '--shortstat', `${t.base}...${t.branch}`])
      done.diff = stat.stdout.trim() || 'no change'
      done.tests = /^Tests:\s*(.*)$/m.exec(e.answer)?.[1]?.trim() ?? 'not reported'
      done.pr = /^## Pull request body\s*\n([\s\S]*)/m.exec(e.answer)?.[1]?.trim() || summary
    }
    await save($, done)
    await refresh($)
    return next(e)
  })

  // Host: D8 holds in code, not only in the brief: a worker may not push, merge or open a pull request.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (e.agentId === undefined || !DELIVERS.test(e.command) || !(await isHost($))) return next(e)
    if (!(await tasks($)).some(t => t.agentId === e.agentId)) return next(e)
    return { deny: 'kiss-mini-agent: only the owner\'s press in the /mini pane pushes, merges or opens a pull request. Commit on your branch and report.' }
  }).catch(($, e, next) =>
    next.called || e.agentId === undefined || !DELIVERS.test(e.command) ? next(e) : { deny: 'kiss-mini-agent: its guard failed; no push, merge or pull request from a subagent.' },
  )

  // Host: its model stays idle; a worker's hand-back or any other prompt but the person's own is dropped.
  on('prompt.submit', async ($, e, next) =>
    (await isHost($)) && e.origin.kind !== 'composer' ? { drop: 'kiss-mini-agent host: handled in code' } : next(e),
  )

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const all = await read($, ledger)
    const ended = all.filter(t => ENDED.includes(t.state)).sort((a, b) => (b.finished ?? 0) - (a.finished ?? 0))
    // An ended task that still holds a worktree stays in view until its Discard.
    const list = [...all.filter(t => !ENDED.includes(t.state)), ...ended.filter((t, i) => i < SHOW_ENDED || t.worktree)]
    return (
      <Box flexDirection="column">
        {list.length === 0 && <Text dimColor>No mini tasks.</Text>}
        {list.map(t => (
          <Box flexDirection="column" key={t.id}>
            <Text>{t.id} {t.kind} {t.state}: {t.title}</Text>
            {t.report && <Text dimColor>{t.report}</Text>}
            {t.state === 'ready' && t.kind === 'code' && <Text>{t.branch} from {t.base}: {t.diff}</Text>}
            {t.state === 'ready' && t.kind === 'code' && <Text>tests: {t.tests}</Text>}
            {DELIVERY.some(([how]) => offers(t, how)) && (
              <Box flexDirection="row" gap={1}>
                {DELIVERY.filter(([how]) => offers(t, how)).map(([how, label]) => (
                  <Button key={`${how}-${t.id}`} label={label} onPress={() => deliver($, t.id, how)} />
                ))}
              </Box>
            )}
          </Box>
        ))}
      </Box>
    )
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const list = await read($, ledger)
    const counts = OPEN.map(s => [s, list.filter(t => t.state === s).length] as const).filter(([, n]) => n > 0)
    if (counts.length === 0) return next(e)
    // Other mods share this slot: theirs is drawn below the counts.
    const below = await next(e).catch(() => undefined)
    const { Box, Text } = $.ui.resolve(e)
    const mine = <Text>mini: {counts.map(([s, n]) => `${n} ${s}`).join(' · ')}</Text>
    return below ? <Box flexDirection="column">{mine}{below}</Box> : mine
  })
}
