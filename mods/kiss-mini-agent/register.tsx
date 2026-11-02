// kiss-mini-agent: /mini in every session, one background host session that runs the workers in code.
// The ledger is `$.store` (shared by every session on the machine): one key per task, one for the host.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { State, Task } from './types'

type $ = EngineInterface

const TASK = 'kiss-mini/task/'
const HOST = 'kiss-mini/host'
const HOST_NAME = 'kiss-mini-agent'
const OPEN: State[] = ['waiting for you', 'working', 'ready', 'watching']
const TOAST: State[] = ['done', 'ready', 'waiting for you', 'failed']
const SUMMARY_MAX = 600

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

function brief(t: Task, rules: string, dir: string) {
  return [
    `# Mini task ${t.id}: ${t.title}`,
    'Kind: question',
    `Checkout: ${t.cwd}    Task folder: ${dir}`,
    'Return: owner    Owner order: yes',
    `Rules: ${rules}`,
    `Summary: answer the owner's question: ${t.title}`,
    'Acceptance checks:',
    '- The answer names the files and lines it rests on.',
    'Out of scope: any change to a file.',
    'Suggested skills: research',
  ].join('\n')
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

/** Host: claims the task, then starts its worker; a task another host claimed is left alone. */
async function run($: $, id: string) {
  const t = (await $.store.get(TASK + id)) as Task | undefined
  if (!t || t.host || t.state !== 'working') return
  await save($, { ...t, host: await $.session.id() })
  const rules = `${$.plugin.root}/skills/kiss-mini-agent/references/handoff.md`
  const r = await $.agent.spawn({
    subagentType: 'kiss:kiss-worker',
    prompt: brief(t, rules, await folder($, id)),
    description: `mini ${id}: ${t.title}`,
    cwd: t.cwd,
  })
  // The worker's turn.start may have written the task meanwhile: build on the stored entry.
  const now = (await $.store.get(TASK + id)) as Task
  if (r.deny !== undefined) await save($, { ...now, state: 'failed', report: r.deny })
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
      description: 'kiss-mini-agent: ask <question> runs it in a background worker; status lists the tasks',
      argumentHint: 'ask <question> | status',
    })
    if (await isHost($)) {
      await $.store.set(HOST, { sessionId: await $.session.id(), beat: await $.clock.now() })
      $.clock.every(60_000, async () => {
        await $.store.set(HOST, { sessionId: await $.session.id(), beat: await $.clock.now() })
      })
      for (const t of await tasks($)) if (t.state === 'working' && !t.host) await run($, t.id)
    }
    $.clock.every(5_000, () => refresh($))
    await refresh($)
    return next(e)
  })

  on('command.run', { command: 'mini' }, async ($, e) => {
    const [verb = 'status', ...rest] = e.args.trim().split(/\s+/)
    if (verb === 'ask' && rest.length > 0) {
      const id = await newId($)
      const now = await $.clock.now()
      await save($, { id, kind: 'question', title: rest.join(' '), sender: await $.session.id(), cwd: await $.session.cwd(), state: 'working', started: now })
      await refresh($)
      return { text: `mini ${id}: question started (${await send($, id)}).` }
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
    await save($, { ...t, state, report: summary, log, finished: await $.clock.now() })
    await refresh($)
    return next(e)
  })

  // Host: its model stays idle; a worker's hand-back or any other prompt but the person's own is dropped.
  on('prompt.submit', async ($, e, next) =>
    (await isHost($)) && e.origin.kind !== 'composer' ? { drop: 'kiss-mini-agent host: handled in code' } : next(e),
  )

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
