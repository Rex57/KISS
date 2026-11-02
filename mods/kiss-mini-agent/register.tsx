// kiss-mini-agent: /mini in every session, one background host session that runs the workers in code.
// The ledger is `$.store` (shared by every session on the machine): one key per task, one for the host.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Delivery, State, Task } from './types'

type $ = EngineInterface

const TASK = 'kiss-mini/task/'
const HOST = 'kiss-mini/host'
const HOST_NAME = 'kiss-mini-agent'
const TOAST: State[] = ['done', 'ready', 'waiting for you', 'failed']
const ENDED: State[] = ['done', 'failed']
const SUMMARY_MAX = 600
const PANE = 'kiss-mini'
const KEEP_MS = 7 * 24 * 3600_000
const WATCH_FIRST = 60_000
const WATCH_IDLE = 600_000
const WATCH_MAX = 24 * 3600_000
const CODE_MAX = 30 * 60_000
const STATUS_EVERY = 30_000
// Code workers at once: 3 from the harness (a hand-off), 1 for the owner's own /mini.
const SLOTS = { harness: 3, owner: 1 }
// The open states, in the order the pane and the band show them.
const ORDER: State[] = ['waiting for you', 'working', 'ready', 'watching']
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
// A command that pushes, merges or opens a pull request: git's push or merge subcommand after any options (quoted
// text, such as a commit message, is not read), gh pr create|merge|ready, or a gh api call that writes to `pulls`.
const GIT_DELIVERS = /\bgit(?:\s+(?:-C\s*\S+|-c\s+\S+|--?[\w-]+(?:=\S+)?))*\s+(?:push|merge)(?=\s|$|[;&|)])/
const GH_DELIVERS = /\bgh\s+pr\s+(?:create|merge|ready)\b|\bgh\s+api\b(?=[^;&|]*pulls)(?=[^;&|]*(?:-X\s*POST|--method[\s=]POST|\s-[fF]\s|--(?:raw-)?field|--input))/
const delivers = (command: string) => GIT_DELIVERS.test(command.replace(/'[^']*'|"(?:[^"\\]|\\.)*"/g, "''")) || GH_DELIVERS.test(command)
const NOT_GIVEN = 'not given: read the files the first line names.'

const isCode = (t: Task) => t.kind === 'code' || t.kind === 'bug'

/** The brief; `text` is the part that may be cut: the owner's task text, or a hand-off's own brief. */
function briefLines(t: Task, text: string, rules: string, dir: string) {
  const where = isCode(t)
    ? [`Checkout: ${t.cwd}    Base: ${t.base}    Branch: ${t.branch}    Worktree: ${t.worktree}`, `Task folder: ${dir}`]
    : [`Checkout: ${t.cwd}    Task folder: ${dir}`]
  if (t.brief !== undefined) {
    return [`# Mini task ${t.id}: ${t.title.slice(0, 120)}`, ...where, `Return: ${t.return ? 'harness' : 'owner'}    Owner order: no`, `Rules: ${rules}`, text].join('\n')
  }
  const head = [`# Mini task ${t.id}: ${text}`, `Kind: ${t.kind}`, ...where, 'Return: owner    Owner order: yes', `Rules: ${rules}`]
  if (t.kind === 'question') {
    return [...head,
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
  return [...head,
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

/** The brief in handoff.md's format, at most 1,500 characters: a text that does not fit is cut, its whole text is in the task folder. */
function brief(t: Task, rules: string, dir: string): { text: string; whole: string; isCut: boolean } {
  const whole = t.brief ?? t.title
  const full = briefLines(t, whole, rules, dir)
  if (full.length <= BRIEF_MAX) return { text: full, whole, isCut: false }
  const more = `... (whole text: ${dir}/task.md)`
  const room = BRIEF_MAX - briefLines(t, '', rules, dir).length - more.length
  return { text: briefLines(t, whole.slice(0, Math.max(0, room)) + more, rules, dir), whole, isCut: true }
}

/** The report as the sender reads it: the report format's lines, the summary cut to 600, the log in the task folder. */
function reportMessage(t: Task, answer: string) {
  const line = (name: string, none: string) => new RegExp(`^${name}:.*$`, 'm').exec(answer)?.[0] ?? `${name}: ${none}`
  return [
    `kiss-mini-agent task ${t.id} (${t.kind}): ${t.title.slice(0, 120)}`,
    `State: ${t.state}`,
    `Summary: ${t.report ?? ''}`,
    line('Branch', 'none'),
    line('Tests', 'not reported'),
    `Full log: ${t.log}`,
  ].join('\n')
}

/** Copies the ledger into the band's state and toasts each of this session's tasks that reached a state for the owner. */
async function refresh($: $) {
  const list = await tasks($)
  await update($, ledger, () => list)
  const me = await $.session.id()
  for (const t of list) {
    if (t.sender !== me) continue
    if ((t.changes ?? 0) > (t.seen ?? 0)) {
      await save($, { ...((await $.store.get(TASK + t.id)) as Task), seen: t.changes })
      $.ui.toast(`mini ${t.id} watch: ${t.title} is ${t.status}`)
    }
    if (t.notified || !TOAST.includes(t.state)) continue
    await save($, { ...(await $.store.get(TASK + t.id) as Task), notified: true })
    $.ui.toast(`mini ${t.id} ${t.state}: ${t.title}${t.kind === 'watch' && t.report ? ` - ${t.report}` : ''}`)
  }
}

/** Host: the ledger forgets ended tasks after 7 days; one that still holds a worktree waits for its Discard. */
async function prune($: $) {
  const now = await $.clock.now()
  for (const t of await tasks($)) {
    if (ENDED.includes(t.state) && !t.worktree && (t.finished ?? t.started) < now - KEEP_MS) await $.store.delete(TASK + t.id)
  }
}

/** Host: one check of a watch, by gh or the command itself; no model is asked. */
async function look($: $, t: Task): Promise<{ state: State; status: string }> {
  const run = (argv: string[]) => $.process.run(argv, { cwd: t.cwd, timeoutMs: 600_000 })
  if (t.watch === 'test') {
    const r = await run(['sh', '-c', t.target!])
    const last = `${r.stdout}\n${r.stderr}`.trim().split('\n').slice(-5).join(' · ')
    return r.exitCode === 0 ? { state: 'done', status: 'passed' } : { state: 'failed', status: `exit ${r.exitCode}: ${last}`.slice(0, SUMMARY_MAX) }
  }
  const r = t.watch === 'pr'
    ? await run(['gh', 'pr', 'view', t.target!, '--json', 'state', '-q', '.state'])
    : await run(['gh', 'run', 'view', t.target!, '--json', 'status,conclusion', '-q', '.status+" "+.conclusion'])
  // A gh that fails (network, auth) is no change: the watch checks again later.
  if (r.exitCode !== 0) return { state: 'watching', status: t.status ?? `gh: ${r.stderr.trim().slice(0, 200)}` }
  const [st = '', end = ''] = r.stdout.trim().toLowerCase().split(/\s+/)
  if (t.watch === 'pr') return st === 'merged' || st === 'closed' ? { state: 'done', status: st } : { state: 'watching', status: st }
  if (st !== 'completed') return { state: 'watching', status: st }
  return end === 'success' ? { state: 'done', status: 'passed' } : { state: 'failed', status: end || 'failed' }
}

/** Host: ends a task's worker by denying its every tool call; its last report is ignored. A slot frees. */
async function stop($: $, t: Task, why: string) {
  await save($, { ...t, state: 'failed', report: why, stopped: true, finished: await $.clock.now() })
  for (const x of await tasks($)) if (!x.host) await run($, x.id)
  await refresh($)
}

/** Host: a worker the engine lists as waiting (a permission ask in the host session) waits for the owner. */
async function waits($: $) {
  const agents = await $.agent.list()
  for (const t of await tasks($)) {
    const status = agents.find(a => a.id === t.agentId)?.status
    if (t.state === 'working' && status === 'waiting') await save($, { ...t, state: 'waiting for you', wait: 'permission', notified: false })
    else if (t.wait === 'permission' && t.state === 'waiting for you' && status === 'running') {
      // The wait does not count toward the 30 minutes.
      await save($, { ...t, state: 'working', wait: undefined, notified: false, claimed: await $.clock.now() })
    }
  }
}

/** Host: checks each watch that is due; a change checks again in a minute, no change waits twice as long, up to 10 minutes. */
async function tick($: $) {
  const now = await $.clock.now()
  const me = await $.session.id()
  await orphans($)
  for (const t of await tasks($)) {
    if (isCode(t) && t.state === 'working' && t.host === me && t.claimed && now - t.claimed > CODE_MAX) await stop($, t, 'timed out after 30 minutes')
    if (t.kind !== 'watch' || t.state !== 'watching' || t.host !== me) continue
    if (now - t.started > WATCH_MAX) {
      await save($, { ...t, state: 'done', report: 'expired', finished: now })
      continue
    }
    if (now < (t.next ?? 0)) continue
    // Claim this check first: a slow command is not started again by the next tick while it runs.
    await save($, { ...t, next: now + WATCH_MAX })
    const { state, status } = await look($, t)
    const at = await $.clock.now()
    const changed = t.status !== undefined && status !== t.status
    // A CI run that is queued or in progress is checked every minute; elsewhere no change doubles the gap.
    const busy = t.watch === 'run' && (status === 'queued' || status === 'in_progress')
    const every = changed || busy ? WATCH_FIRST : Math.min(WATCH_IDLE, (t.every ?? WATCH_FIRST / 2) * 2)
    const ended = state !== 'watching' ? { report: status, finished: at } : {}
    // An end toasts by its state; only a change along the way counts as a change to toast.
    const changes = (t.changes ?? 0) + (changed && state === 'watching' ? 1 : 0)
    const cur = (await $.store.get(TASK + t.id)) as Task
    if (cur.state === 'watching') await save($, { ...cur, state, status, every, next: at + every, changes, ...ended })
  }
  await refresh($)
}

/** Host: a task claimed by a host that is no longer the live one is the live host's now: a watch goes on, a worker's task
 * fails (its worker ended with its session) and frees its slot. */
async function orphans($: $) {
  const me = await $.session.id()
  for (const t of await tasks($)) {
    if (!t.host || t.host === me || ENDED.includes(t.state) || t.state === 'ready') continue
    if (t.kind === 'watch') await save($, { ...t, host: me })
    else await stop($, t, 'its host session ended')
  }
}

/** Host: a small model writes the one-line status from a worker's recent tool calls. */
async function statusLine($: $, id: string, title: string, calls: string[]) {
  const m = await $.model.complete({
    model: 'haiku',
    prompt: `A coding agent works on: ${title.slice(0, 200)}\nIts last tool calls:\n${calls.join('\n')}\nSay in one line of at most 60 characters what it does now. Only the line.`,
  })
  const line = m.isAnswered ? m.text.trim().split('\n')[0]?.slice(0, 80) : undefined
  const cur = (await $.store.get(TASK + id)) as Task | undefined
  if (cur && !cur.stopped && line && line !== cur.status) await save($, { ...cur, status: line })
  await refresh($)
}

/** Host: claims the task, then starts its worker (a watch: its first check); a task another host claimed is left alone. */
async function run($: $, id: string) {
  const t = (await $.store.get(TASK + id)) as Task | undefined
  if (!t || t.host || t.state !== (t.kind === 'watch' ? 'watching' : 'working')) return
  if (isCode(t)) {
    const harness = t.brief !== undefined
    const busy = (await tasks($)).filter(x => isCode(x) && x.host && x.state === 'working' && (x.brief !== undefined) === harness)
    if (busy.length >= SLOTS[harness ? 'harness' : 'owner']) return
  }
  const claimed = await $.clock.now()
  await save($, { ...t, host: await $.session.id(), claimed, ...(t.kind === 'watch' ? { next: claimed } : {}) })
  // The host's minute timer checks a watch: a check never runs inside the message that brought the task.
  if (t.kind === 'watch') return
  if (isCode(t)) {
    const made = await $.process.run(['git', '-C', t.cwd, 'worktree', 'add', '-b', t.branch!, t.worktree!, t.base!])
    // No worktree was made: nothing is left to Discard.
    if (made.exitCode !== 0) {
      return save($, { ...t, state: 'failed', report: made.stderr.trim().slice(0, SUMMARY_MAX), worktree: undefined, branch: undefined, finished: await $.clock.now() })
    }
  }
  const rules = `${$.plugin.root}/skills/kiss-mini-agent/references/handoff.md`
  const dir = await folder($, id)
  const b = brief(t, rules, dir)
  if (b.isCut) await $.fs.write(`${dir}/task.md`, b.whole)
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
/** Sender: one message to the host (a task, an answer, a stop); a new host when none takes it. */
async function wake($: $, text: string) {
  const host = (await $.store.get(HOST)) as { sessionId: string } | undefined
  if (host && (await $.session.send({ to: { sessionId: host.sessionId }, text })).isDelivered) return 'sent'
  // No prompt: the host's own model never runs. Haiku in case the person attaches and types. The flag rides in
  // --settings: a session started from a background session does not get the caller's environment.
  const settings = JSON.stringify({ env: { KISS_MINI_HOST: '1' } })
  await $.process.run(['claude', '--bg', '--name', HOST_NAME, '--model', 'haiku', '--plugin-dir', $.plugin.root, '--settings', settings])
  return 'started a new host'
}

const DELIVERY: [Delivery, string][] = [['merge', 'Merge into the base'], ['push', 'Push'], ['pr', 'Draft PR'], ['discard', 'Discard']]

/** Whether the pane offers this delivery: Discard for any code task that still has a worktree, the others when ready. */
const offers = (t: Task, how: Delivery) =>
  isCode(t) && !t.busy && (how === 'discard' ? !!t.worktree && t.state !== 'working' : t.state === 'ready')

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
      else if (merging || unmerged) r = { exitCode: 1, stdout: '', stderr: `a merge is under way in ${t.cwd}: finish or abort it first` }
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
    const removed = await git('worktree', 'remove', '--force', t.worktree)
    if (how === 'discard') await git('branch', '-D', t.branch)
    // A worktree git no longer lists (its folder deleted, then pruned) is gone too.
    const gone = removed.exitCode === 0 || !(await git('worktree', 'list', '--porcelain')).stdout.split('\n').includes(`worktree ${t.worktree}`)
    if (!gone) $.ui.toast(`mini ${id}: worktree kept at ${t.worktree}: ${removed.stderr.trim().replace(/\s*\n\s*/g, ' · ').slice(0, 200)}`)
    const { pr, diff, tests, ...rest } = t
    await save($, { ...rest, state: 'done', delivered: how, ...(gone ? { worktree: undefined } : {}) })
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
      argumentHint: '<task> [--base <branch>] | ask <question> | watch pr <n> | watch run <id> | watch <test command> | stop <id> | status',
    })
    await $.tool.register({
      name: 'handoff',
      description:
        'kiss-mini-agent: hand a side task (outside the current tickets) to a background worker. kind: code, bug or question; ' +
        'brief: in the format of skills/kiss-mini-agent/references/handoff.md, at most 1,500 characters; base: the branch a code ' +
        'or bug task starts from (the harness branch); return: true sends the report back to this session as one message.',
      inputSchema: {
        type: 'object',
        properties: {
          kind: { type: 'string', enum: ['code', 'bug', 'question'] },
          title: { type: 'string' },
          brief: { type: 'string', maxLength: BRIEF_MAX },
          base: { type: 'string' },
          return: { type: 'boolean' },
        },
        required: ['kind', 'title', 'brief'],
      },
      isDeferred: false,
    })
    if (await isHost($)) {
      await $.tool.register({
        name: 'progress',
        description: 'kiss-mini-agent workers: report your plan\'s step as you start it: step (1-based) of total steps.',
        inputSchema: { type: 'object', properties: { step: { type: 'number' }, total: { type: 'number' } }, required: ['step', 'total'] },
        isDeferred: false,
      })
      await $.store.set(HOST, { sessionId: await $.session.id(), beat: await $.clock.now() })
      await prune($)
      await orphans($)
      $.clock.every(60_000, async () => {
        await $.store.set(HOST, { sessionId: await $.session.id(), beat: await $.clock.now() })
        await prune($)
        await tick($)
      })
      for (const t of await tasks($)) if (!t.host) await run($, t.id)
    }
    $.clock.every(5_000, async () => {
      if (await isHost($)) await waits($)
      await refresh($)
    })
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
      const t: Task = { id, kind: 'question', title: rest.join(' '), sender: await $.session.id(), cwd, state: 'working', started: await $.clock.now(), key: crypto.randomUUID() }
      if (verb === 'stop') {
        const known = (await $.store.get(TASK + (rest[0] ?? ''))) as Task | undefined
        if (!known) return { text: `mini: no task ${rest[0] ?? ''}. /mini status lists them.` }
        return { text: `mini ${known.id}: stop asked (${await wake($, `KISS-MINI stop ${known.id} ${known.key}`)}).` }
      }
      if (verb === 'watch') {
        const what = rest[0] === 'pr' || rest[0] === 'run' ? rest[0] : 'test'
        Object.assign(t, { kind: 'watch', state: 'watching', watch: what, target: (what === 'test' ? rest : rest.slice(1)).join(' ') })
        if (!t.target) return { text: 'mini: watch pr <number|url>, watch run <id|url>, or watch <test command>.' }
      } else if (verb !== 'ask') {
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
      return { text: `mini ${id}: ${t.kind} started (${await wake($, `KISS-MINI task ${id}`)}).` }
    }
    const lines = (await tasks($)).map(t => `${t.id} ${t.kind} ${t.state}: ${t.title}${t.report ? ` - ${t.report}` : ''}`)
    return { text: lines.join('\n') || 'mini: no tasks.' }
  })

  // Any session: the hand-off tool records a task and wakes the host, as /mini does.
  on('tool.call', { tool: 'mcp__kiss__handoff' }, async ($, e) => {
    const a = e as unknown as { kind: Task['kind']; title: string; brief: string; base?: string; return?: boolean }
    if (!['code', 'bug', 'question'].includes(a.kind) || !a.title || !a.brief) return { result: 'kiss-mini-agent: kind (code, bug or question), title and brief are needed.' }
    if (a.brief.length > BRIEF_MAX) return { result: `kiss-mini-agent: the brief has ${a.brief.length} characters; at most ${BRIEF_MAX}.` }
    const id = await newId($)
    const cwd = await $.session.cwd()
    const t: Task = { id, kind: a.kind, title: a.title, brief: a.brief, return: a.return === true, sender: await $.session.id(), cwd, state: 'working', started: await $.clock.now(), key: crypto.randomUUID() }
    if (isCode(t)) {
      const base = a.base || (await $.process.run(['git', '-C', cwd, 'rev-parse', '--abbrev-ref', 'HEAD'])).stdout.trim()
      if (!base || base === 'HEAD') return { result: `kiss-mini-agent: ${cwd} is on no branch: give a base.` }
      Object.assign(t, { base, branch: `mini/${id}`, worktree: `${await folder($, id)}/wt` })
    }
    await save($, t)
    await refresh($)
    return { result: `kiss-mini-agent task ${id} (${t.kind}) started (${await wake($, `KISS-MINI task ${id}`)}).${t.return ? ' Its report comes back to this session as one message.' : ''}` }
  })

  // Host: a worker's progress tool sets its step n of m.
  on('tool.call', { tool: 'mcp__kiss__progress' }, async ($, e) => {
    const a = e as unknown as { step: number; total: number; agentId?: string }
    const t = (await tasks($)).find(x => a.agentId !== undefined && x.agentId === a.agentId)
    if (t) await save($, { ...t, step: a.step, total: a.total })
    return { result: t ? `step ${a.step} of ${a.total} noted` : 'kiss-mini-agent: no task runs in this loop.' }
  })

  // Host: each tool call of a worker is its last tool call; after a new one, at most every 30 s, a small model
  // writes the one-line status from the recent calls.
  on('tool.call', async ($, e, next) => {
    if (e.agentId === undefined || !(await isHost($))) return next(e)
    const t = (await tasks($)).find(x => x.agentId === e.agentId)
    if (t?.stopped) return { deny: `kiss-mini-agent: the owner stopped this task (${t.report}). Make no more tool calls; end now.` }
    const r = await next(e)
    if (!t || String(e.tool) === 'mcp__kiss__progress') return r
    const a = e as unknown as Record<string, unknown>
    const arg = [a.command, a.file_path, a.pattern, a.description, a.url].find(v => typeof v === 'string') as string | undefined
    const call = `${String(e.tool)} ${arg ?? ''}`.trim().slice(0, 100)
    // The task may have changed while the tool ran (a stop, a timeout, an answer): build on the stored entry.
    const fresh = (await $.store.get(TASK + t.id)) as Task | undefined
    if (!fresh || fresh.stopped) return r
    const calls = [...(fresh.calls ?? []), call].slice(-5)
    const now = await $.clock.now()
    const due = now - (fresh.statusAt ?? 0) >= STATUS_EVERY
    await save($, { ...fresh, lastTool: call, calls, ...(due ? { statusAt: now } : {}) })
    // The status line does not hold up the worker's tool result.
    if (due) void statusLine($, t.id, fresh.title, calls)
    await refresh($)
    return r
  })

  // Host: a task message is taken in code, so the host's own model makes no turn for it.
  on('session.receive', async ($, e, next) => {
    const [, verb, id = '', key = '', text = ''] = /KISS-MINI (task|answer|stop) (\S+)(?: (\S+))?\n?([\s\S]*?)(?:<\/cross-session-message>|$)/.exec(e.text) ?? []
    if (!verb || !(await isHost($))) return next(e)
    const t = (await $.store.get(TASK + id)) as Task | undefined
    // An answer or a stop carries the task's key, which only the mod reads from the ledger: no model can write one.
    const owner = !!t?.key && key === t.key
    if (verb === 'task') await run($, id)
    else if (verb === 'stop' && owner && t && !ENDED.includes(t.state)) await stop($, t, 'stopped')
    else if (verb === 'answer' && owner && t?.agentId && t.state === 'waiting for you' && t.wait !== 'permission') {
      // The same worker takes the answer and goes on: a finished subagent is resumed with the message. The wait does
      // not count toward the 30 minutes.
      await save($, { ...t, state: 'working', notified: false, report: undefined, claimed: await $.clock.now() })
      await $.session.send({ to: { agentId: t.agentId }, text: `The owner answers your question: ${text.trim()}` })
      await refresh($)
    }
    return { consumed: `kiss-mini-agent ${verb} ${id}` }
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
    if (!t || t.stopped) return next(e)
    const { state, summary } = parseReport(e.answer)
    const log = `${await folder($, t.id)}/report.md`
    await $.fs.write(log, e.answer)
    const fields: Partial<Task> = { state, report: summary, log, finished: await $.clock.now() }
    if (isCode(t)) {
      const stat = await $.process.run(['git', '-C', t.cwd, 'diff', '--shortstat', `${t.base}...${t.branch}`])
      fields.diff = stat.stdout.trim() || 'no change'
      fields.tests = /^Tests:\s*(.*)$/m.exec(e.answer)?.[1]?.trim() ?? 'not reported'
      fields.pr = /^## Pull request body\s*\n([\s\S]*)/m.exec(e.answer)?.[1]?.trim() || summary
    }
    // A stop may have landed while the report was written: it stands.
    const fresh = (await $.store.get(TASK + t.id)) as Task
    if (fresh.stopped) return next(e)
    const done: Task = { ...fresh, ...fields }
    await save($, done)
    // A slot is free: start the tasks that wait for one.
    for (const x of await tasks($)) if (!x.host) await run($, x.id)
    if (t.return) await $.session.send({ to: { sessionId: t.sender }, text: reportMessage(done, e.answer) })
    await refresh($)
    return next(e)
  })

  // Host: D8 holds in code, not only in the brief: a worker may not push, merge or open a pull request.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (e.agentId === undefined || !delivers(e.command) || !(await isHost($))) return next(e)
    if (!(await tasks($)).some(t => t.agentId === e.agentId)) return next(e)
    return { deny: 'kiss-mini-agent: only the owner\'s press in the /mini pane pushes, merges or opens a pull request. Commit on your branch and report.' }
  }).catch(($, e, next) =>
    next.called || e.agentId === undefined || !delivers(e.command) ? next(e) : { deny: 'kiss-mini-agent: its guard failed; no push, merge or pull request from a subagent.' },
  )

  // Host: its model stays idle; a worker's hand-back or any other prompt but the person's own is dropped.
  on('prompt.submit', async ($, e, next) =>
    (await isHost($)) && e.origin.kind !== 'composer' ? { drop: 'kiss-mini-agent host: handled in code' } : next(e),
  )

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    // Mobile draws no Input: there the owner answers from another surface.
    const Input = e.surface === 'mobile' ? undefined : ($.ui.resolve(e) as { Input?: any }).Input
    const all = await read($, ledger)
    const ended = all.filter(t => ENDED.includes(t.state)).sort((a, b) => (b.finished ?? 0) - (a.finished ?? 0))
    // An ended task that still holds a worktree stays in view until its Discard.
    // Waiting for the owner first, then working, ready, watching; then the ended ones, newest first.
    const open = all.filter(t => !ENDED.includes(t.state)).sort((a, b) => ORDER.indexOf(a.state) - ORDER.indexOf(b.state))
    const list = [...open, ...ended.filter((t, i) => i < SHOW_ENDED || t.worktree)]
    const now = await $.clock.now()
    const age = (t: Task) => {
      const s = Math.round(((t.finished ?? now) - t.started) / 1000)
      return s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${Math.round(s / 3600)}h`
    }
    return (
      <Box flexDirection="column">
        {list.length === 0 && <Text dimColor>No mini tasks.</Text>}
        {list.map(t => (
          <Box flexDirection="column" key={t.id}>
            <Text>{`${t.id} ${t.kind} ${t.state}: ${t.title}${t.step ? ` · step ${t.step} of ${t.total}` : ''} · ${age(t)}`}</Text>
            {t.report && <Text dimColor>{t.report}</Text>}
            {!t.report && t.status && <Text dimColor>{t.status}</Text>}
            {t.state === 'working' && t.lastTool && <Text dimColor>{t.lastTool}</Text>}
            {t.state === 'waiting for you' && t.wait === 'permission' && (
              <Text color="warning">waits for a permission in the host session: claude attach {(t.host ?? '').slice(0, 8)}</Text>
            )}
            {Input && t.state === 'waiting for you' && t.wait !== 'permission' && t.agentId && (
              <Input key={`answer-${t.id}`} placeholder="your answer" submitLabel="Send" onSubmit={(text: string) => void wake($, `KISS-MINI answer ${t.id} ${t.key}\n${text}`)} />
            )}
            {t.state === 'ready' && isCode(t) && <Text>{t.branch} from {t.base}: {t.diff}</Text>}
            {t.state === 'ready' && isCode(t) && <Text>tests: {t.tests}</Text>}
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
    const counts = ORDER.map(s => [s, list.filter(t => t.state === s).length] as const).filter(([, n]) => n > 0)
    if (counts.length === 0) return next(e)
    // Other mods share this slot: theirs is drawn below the counts.
    const below = await next(e).catch(() => undefined)
    const { Box, Button, Text } = $.ui.resolve(e)
    const open = () => $.ui.open({ id: PANE, title: 'mini' })
    const mine = (
      <Button key="mini-open" plain onPress={open}>
        <Text>mini: {counts.map(([s, n]) => `${n} ${s}`).join(' · ')}</Text>
      </Button>
    )
    return below ? <Box flexDirection="column">{mine}{below}</Box> : mine
  })
}
