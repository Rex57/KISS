// kiss-mini: /kiss-mini in every session, one background host session that runs the workers in code.
// The ledger is `$.store` (shared by every session on the machine): one key per task, one for the host.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Delivery, State, Task } from './types'

type $ = EngineInterface

const TASK = 'kiss-mini/task/'
const HOST = 'kiss-mini/host'
const HOST_NAME = 'kiss-mini'
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
// Code workers at once: 3 from the harness (a hand-off), 1 for the owner's own /kiss-mini.
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
export function parseReport(answer: string, kind?: Task['kind']): { state: State; summary: string } {
  if (!answer.trim()) return { state: 'failed', summary: 'the worker returned no answer' }
  const state = /^State:\s*(ready|done|failed|waiting for you)\b/im.exec(answer)?.[1]?.toLowerCase() as State | undefined
  const summary = /^Summary:\s*([\s\S]*?)(?=^\w[\w ]*:|\n\n|$(?![\s\S]))/im.exec(answer)?.[1]?.trim() ?? answer.trim()
  // A question answered with no State line is an answer: done. A change with none is not known to be done.
  return { state: state ?? (kind === 'question' ? 'done' : 'failed'), summary: summary.slice(0, SUMMARY_MAX) }
}

const BRIEF_MAX = 1500
const NO_HOST = 'could not start a host'
const HOST_GONE = 3 * 60_000
// A command that pushes, merges or opens a pull request: git's push or merge subcommand after any options (quoted
// text, such as a commit message, is not read), gh pr create|merge|ready, or a gh api call that writes to `pulls`.
const GIT_DELIVERS = /\bgit(?:\s+(?:-C\s*\S+|-c\s+\S+|--?[\w-]+(?:=\S+)?))*\s+(?:subtree\s+)?(?:push|merge)(?=\s|$|[;&|)'"])/
// A git alias that is push or merge under another name.
const GIT_ALIAS = /\bgit\b[^;&|]*-c\s*['"]?alias\.[\w-]+=[^;&|]*\b(?:push|merge)\b/
const GH_DELIVERS = /\bgh\s+pr\s+(?:create|merge|ready)\b|\bgh\s+api\b(?=[^;&|]*pulls\/\d+\/merge)|\bgh\s+api\b(?=[^;&|]*pulls)(?=[^;&|]*(?:-X\s*POST|--method[\s=]POST|\s-[fF]\s|--(?:raw-)?field|--input))/
// Quoted text is not read (a commit message), except where a shell (after its first flag that holds c) or eval runs it
// as a command, and the $(...) or backtick text inside double quotes.
const RUNS_TEXT = /\b(?:(?:bash|sh|zsh)(?:\s+-[a-zA-Z]+)*?\s+-[a-zA-Z]*c[a-zA-Z]*|eval)\s+(?:'([^']*)'|"((?:[^"\\]|\\.)*)")/g
const RUNS_IN_QUOTES = /\$\(|`/
// A double-quoted word; a $(...) in it may hold quotes of its own and one more level of parentheses.
const DQ = /"((?:[^"\\$`]|\\.|\$\((?:[^()'"]|'[^']*'|"(?:[^"\\]|\\.)*"|\([^()]*\))*\)|`[^`]*`|\$)*)"/
// A line that feeds a heredoc to a shell or eval (bash <<EOF, cat <<EOF | sh): its body runs.
const RUNS_SHELL = /(?:^|[\s;&|(`])(?:[^\s;&|()`]*\/)?(?:bash|sh|zsh|eval)(?=$|[\s;&|)`])/
/** `command` without its heredoc bodies (text, such as a commit message), except a body a shell or eval runs; each
 * delimiter line stays. A << inside (( )) is a shift. */
function unheredoc(command: string): string {
  const lines = command.split('\n')
  const out: string[] = []
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!
    out.push(line)
    if (RUNS_SHELL.test(line)) continue
    for (const m of line.matchAll(/(?<!<)<<(?!<)(-?)[ \t]*(['"]?)([A-Za-z_][\w.-]*)\2/g)) {
      const before = line.slice(0, m.index)
      if ((before.match(/\(\(/g) ?? []).length > (before.match(/\)\)/g) ?? []).length) continue
      while (i + 1 < lines.length && (m[1] ? lines[i + 1]!.replace(/^\t+/, '') : lines[i + 1]) !== m[3]) i++
      if (i + 1 < lines.length) out.push(lines[++i]!)
    }
  }
  return out.join('\n')
}
function delivers(raw: string) {
  const command = unheredoc(raw)
  return GIT_DELIVERS.test(command.replace(new RegExp(`'[^']*'|${DQ.source}`, 'g'), "''")) ||
    [...command.matchAll(RUNS_TEXT)].some(m => GIT_DELIVERS.test(m[1] ?? m[2] ?? '')) ||
    [...command.matchAll(new RegExp(DQ.source, 'g'))].some(m => RUNS_IN_QUOTES.test(m[1]!) && GIT_DELIVERS.test(m[1]!)) ||
    GIT_ALIAS.test(command) || GH_DELIVERS.test(command)
}
// D1, D2: a code or bug worker writes only in its worktree; outside it, git only reads.
const ONLY_WORKTREE = 'kiss-mini: a worker writes only in its worktree'
const GIT_READS = ['status', 'log', 'diff', 'show', 'rev-parse', 'rev-list', 'ls-files', 'cat-file', 'blame', 'grep', 'merge-base', 'describe']
const FILE_TOOLS = ['Edit', 'Write', 'NotebookEdit']
/** `p` from the folder `base`, with `.` and `..` resolved and `/private/var|tmp` read as `/var|tmp`; undefined when `~`
 * or a variable other than $PWD leaves it unknown. */
function resolve(base: string | undefined, p: string): string | undefined {
  const full = p.replace(/^\$\{?PWD\}?(?=\/|$)/, base ?? '$')
  if (/^~|[$`]/.test(full) || (!full.startsWith('/') && base === undefined)) return undefined
  const parts: string[] = []
  for (const part of (full.startsWith('/') ? full : `${base}/${full}`).split('/')) {
    if (part === '..') parts.pop()
    else if (part && part !== '.') parts.push(part)
  }
  return `/${parts.join('/')}`.replace(/^\/private(?=\/(?:var|tmp)(?:\/|$))/, '')
}
const inside = (p: string | undefined, wt: string | undefined) => !!p && !!wt && (p === wt || p.startsWith(`${wt}/`))
/** A shell command's words, cut into segments at each operator (; & | ( ) a backtick, a new line); quoted text is part
 * of a word, never an operator or a word of its own. */
const WORDS = new RegExp([/'([^']*)'/.source, DQ.source, /\\(.)|([;&|()`\n])|(\s)|([^\s'"\\;&|()`]+)/.source].join('|'), 'g')
function segments(command: string): string[][] {
  const all: string[][] = [[]]
  let word: string | undefined
  const end = () => {
    if (word !== undefined) all[all.length - 1]!.push(word)
    word = undefined
  }
  for (const m of command.replace(/\\\n/g, '').matchAll(WORDS)) {
    if (m[4]) {
      end()
      all.push([])
    } else if (m[5]) end()
    else {
      // $(...) and backtick text inside double quotes runs, before the command that holds the word.
      if (m[2] && RUNS_IN_QUOTES.test(m[2])) all.splice(all.length - 1, 0, ...segments(m[2]))
      word = (word ?? '') + (m[1] ?? m[2]?.replace(/\\(.)/g, '$1') ?? m[3] ?? m[6])
    }
  }
  end()
  return all
}
/** Whether a git command in `command`, run from `dir`, writes in a folder outside `wt`: its -C folders (each from the one
 * before), --git-dir, --work-tree, GIT_DIR= and GIT_WORK_TREE=, after a cd or pushd; bash|sh|zsh -c and eval text runs too. */
function gitOutside(command: string, dir: string | undefined, wt: string | undefined, env: Record<string, string | undefined> = {}): boolean {
  for (const seg of segments(unheredoc(command))) {
    for (let i = 0; i < seg.length; i++) {
      const w = seg[i]!
      const set = /^(GIT_DIR|GIT_WORK_TREE)=(.*)$/s.exec(w)
      if (set) env[set[1]!] = resolve(dir, set[2]!)
      else if (w === 'cd' || w === 'pushd') {
        // -- and the flags are no folder; cd - (the host's folder, after the mod's cd) and pushd +N leave it unknown.
        const to = seg.slice(i + 1).find(a => !/^(?:-[LPe@]+|--)$/.test(a)) ?? '~'
        dir = /^[-+]/.test(to) ? undefined : resolve(dir, to)
      } else if (/(?:^|\/)(?:bash|sh|zsh)$/.test(w)) {
        // The text after the shell's first flag that holds c (bash -e -c, /bin/sh -xc) runs.
        const c = seg.findIndex((a, k) => k > i && /^-[a-zA-Z]*c[a-zA-Z]*$/.test(a))
        if (c > 0 && gitOutside(seg[c + 1] ?? '', dir, wt, { ...env })) return true
      } else if (w === 'eval' && gitOutside(seg.slice(i + 1).join(' '), dir, wt, { ...env })) return true
      else if (w === 'git' || w.endsWith('/git')) {
        const folders = Object.keys(env).map(k => env[k])
        let here = dir
        let sub: string | undefined
        let j = i + 1
        for (; j < seg.length && sub === undefined; j++) {
          const a = seg[j]!
          const eq = a.startsWith('--') ? a.indexOf('=') : -1
          const [opt, given] = eq > 0 ? [a.slice(0, eq), a.slice(eq + 1)] : /^-C./.test(a) ? ['-C', a.slice(2)] : [a, undefined]
          const value = () => given ?? seg[++j] ?? ''
          if (opt === '-C' || opt === '--git-dir' || opt === '--work-tree') {
            const v = value()
            // An unquoted $(...) or backtick value cuts the command there: its folder is unknown and its verb unseen.
            if (v === '' || v === '$') return true
            if (opt === '-C') here = resolve(here, v)
            else folders.push(resolve(here, v))
          }
          else if (['-c', '--namespace', '--config-env'].includes(opt)) value()
          else if (!a.startsWith('-')) sub = a
        }
        const args = seg.slice(j)
        // D22: refs/stash and the worktree list are shared by every worktree, so a worker's stash or worktree change
        // reaches outside from anywhere. --output writes a file, also from a read verb (diff, log, show).
        if (sub === 'stash' || (sub === 'worktree' && args[0] !== 'list')) return true
        const output = args.flatMap((a, k) => (a === '--output' ? [args[k + 1] ?? ''] : a.startsWith('--output=') ? [a.slice(9)] : []))
        if (sub !== undefined && (!GIT_READS.includes(sub) || output.length > 0) &&
          [here, ...folders, ...output.map(o => resolve(here, o))].some(f => !inside(f, wt))) return true
      }
    }
  }
  return false
}
/** Whether a worker's tool call writes outside its worktree `wt`; with no `wt` known, every write does. A Bash command
 * starts in the host's folder, unknown here: only the mod's cd before it puts it in the worktree. */
function writesOutside(e: Record<string, unknown>, worktree?: string): boolean {
  const wt = worktree === undefined ? undefined : resolve('/', worktree)
  if (FILE_TOOLS.includes(String(e.tool))) return !inside(resolve(wt, String(e.file_path ?? e.notebook_path ?? '')), wt)
  return String(e.tool) === 'Bash' && gitOutside(String(e.command ?? ''), undefined, wt)
}
// A GitHub tool of an MCP server that writes (a pull request, a merge, a push).
const GITHUB_WRITES = /^mcp__.*github.*__.*(?:create|merge|update|push|delete)/i
const NOT_GIVEN = 'not given: read the files the first line names.'
const TEXT_MIN = 200

const isCode = (t: Task) => t.kind === 'code' || t.kind === 'bug'
/** What starts a worker's Bash command (D21, D24): a cd to its own folder `home` (a question: its checkout, after the
 * export that turns off the Python and pytest caches). The brief names it; the mod puts it before a command that lacks it. */
const bashPrefix = (t: Task, home = `'${(t.worktree ?? t.cwd).replace(/'/g, `'\\''`)}'`) =>
  `${t.kind === 'question' ? 'export PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS="-p no:cacheprovider"; ' : ''}cd ${home} && `

/** The brief; `text` is the part that may be cut: the owner's task text, or a hand-off's own brief. */
function briefLines(t: Task, text: string, rules: string, dir: string, seed = false, short = false) {
  // Short: the lines that only say "not given" go first, before any of the task's own text.
  const given = (line: string) => !(short && line.endsWith(NOT_GIVEN))
  const where = [...(isCode(t)
    ? [`Checkout: ${t.cwd}    Base: ${t.base}    Branch: ${t.branch}    Worktree: ${t.worktree}`, `Task folder: ${dir}`]
    : [`Checkout: ${t.cwd} (read only)    Task folder: ${dir}`]),
  // The folder by its field's name: the path is on the line above, and a second copy would cost the task text its length.
  `Bash: ${bashPrefix(t, isCode(t) ? "'<Worktree>'" : "'<Checkout>'")}<command>`,
  // $PWD is W: the worker starts in its worktree (a question: its checkout); after a cd into the Checkout, -p "$PWD"
  // would query the base branch's index. Two full paths here would cost the task text 150 characters.
  ...(seed ? ['CodeGraph (never cd first): codegraph explore|node|callers -p "$PWD" <names>; codegraph sync -q "$PWD" after edits; seed: seed.md in the Task folder'] : [])]
  // The report's first line and the progress tool are in the brief itself: a worker may not open the Rules file.
  const rule = 'Report: your final message starts "State: done|ready|failed|waiting for you", then "Summary:". Call mcp__kiss__progress (step, total) as you start each step.'
  if (t.brief !== undefined) {
    return [`# Mini task ${t.id}: ${t.title.slice(0, 120)}`, ...where, `Return: ${t.return ? 'harness' : 'owner'}    Checks: run`, `Rules: ${rules}`, rule, text].join('\n')
  }
  const head = [`# Mini task ${t.id}: ${text}`, `Kind: ${t.kind}`, ...where, `Return: owner    Checks: ${t.now ? 'skip (owner)' : 'run'}`, `Rules: ${rules}`, rule]
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
    ].filter(given).join('\n')
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
    'Suggested skills: ponytail first, tdd, CodeGraph; pr for the pull request body',
  ].filter(given).join('\n')
}

/** The brief in handoff.md's format, at most 1,500 characters: a text that does not fit is cut, its whole text is in the task folder. */
function brief(t: Task, rules: string, dir: string, seed = false): { text: string; whole: string; isCut: boolean } {
  const whole = t.brief ?? t.title
  const full = briefLines(t, whole, rules, dir, seed)
  if (full.length <= BRIEF_MAX) return { text: full, whole, isCut: false }
  const short = briefLines(t, whole, rules, dir, seed, true)
  if (short.length <= BRIEF_MAX) return { text: short, whole, isCut: false }
  const more = `... (whole text: ${dir}/task.md)`
  // At least the first 200 characters of the task's own text stay in the brief.
  // shortcut: a brief can pass 1,500 characters when the paths alone leave less than 200 characters for the task text;
  // upgrade: shorten the paths in the brief, for example to names relative to the task folder.
  const room = Math.max(TEXT_MIN, BRIEF_MAX - briefLines(t, '', rules, dir, seed, true).length - more.length)
  return { text: briefLines(t, whole.slice(0, room) + more, rules, dir, seed, true), whole, isCut: true }
}

/** Host: when the checkout has a CodeGraph index, indexes the worker's worktree and saves `codegraph explore` on the task's words as T/seed.md. */
async function seedFile($: $, t: Task, dir: string): Promise<boolean> {
  // The index sits at the repo's root, also when the task started in a subfolder.
  const top = (await $.process.run(['git', '-C', t.cwd, 'rev-parse', '--show-toplevel']).catch(() => undefined))?.stdout.trim() || t.cwd
  const w = t.worktree ?? top
  // A missing or slow codegraph is no seed, never a failed task.
  const cg = (...argv: string[]) => $.process.run(['codegraph', ...argv], { cwd: w, timeoutMs: 600_000 }).catch(() => undefined)
  if (!(await cg('status', top))?.stdout.includes(`Project: ${top}\n`)) return false
  if (w !== top && (await cg('init', '-y', w))?.exitCode !== 0) return false
  const r = await cg('explore', '-p', w, t.title.slice(0, 200))
  if (r?.exitCode !== 0 || !r.stdout.trim()) return false
  await $.fs.write(`${dir}/seed.md`, r.stdout)
  return true
}

/** The report as the sender reads it: the report format's lines, the summary cut to 600, the log in the task folder. */
function reportMessage(t: Task, answer: string) {
  const line = (name: string, none: string) => new RegExp(`^${name}:.*$`, 'm').exec(answer)?.[0] ?? `${name}: ${none}`
  return [
    `kiss-mini task ${t.id} (${t.kind}): ${t.title.slice(0, 120)}`,
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
      $.ui.toast(`kiss-mini ${t.id} watch: ${t.title} is ${t.status}`)
    }
    if (t.notified || !TOAST.includes(t.state)) continue
    await save($, { ...(await $.store.get(TASK + t.id) as Task), notified: true })
    $.ui.toast(`kiss-mini ${t.id} ${t.state}: ${t.title}${t.kind === 'watch' && t.report ? ` - ${t.report}` : ''}`)
  }
}

/** Host: the ledger forgets ended tasks after 7 days; one that still holds a worktree or a branch waits for its Discard. */
async function prune($: $) {
  const now = await $.clock.now()
  for (const t of await tasks($)) {
    if (ENDED.includes(t.state) && !holds(t) && (t.finished ?? t.started) < now - KEEP_MS) await $.store.delete(TASK + t.id)
  }
}

/** What a watch checks: `pr <n>`, `run <id>`, or else a test command. */
function watchOf(words: string[]) {
  const what = words[0] === 'pr' || words[0] === 'run' ? words[0] : 'test'
  return { watch: what as Task['watch'], target: (what === 'test' ? words : words.slice(1)).join(' ') }
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
    // A ready task whose commits are already in its base was merged (by the harness, by hand): it is done. A branch
    // with no commit of its own is in its base too, so it counts only with commits at its report. Its git runs in the
    // task's own repository: a harness task's sender folder (the run's worktree) is gone after the run's merge.
    if (isCode(t) && t.state === 'ready' && t.host === me && t.branch && t.worktree && !t.busy && (t.ahead ?? 0) > 0) {
      const repo = await repoOf($, t)
      if ((await $.process.run(['git', '-C', repo, 'merge-base', '--is-ancestor', t.branch, t.base!])).exitCode === 0) {
        // A worktree with changes nobody committed is never forced away.
        // The index the seed made (`?? .codegraph/`) is no change of the worker's.
        const dirty = (await $.process.run(['git', '-C', t.worktree, 'status', '--porcelain'])).stdout.split('\n')
          .filter(l => l.trim() && l.trim() !== '?? .codegraph/').join('\n')
        if (dirty) $.ui.toast(`kiss-mini ${t.id}: merged; worktree kept, it has uncommitted changes: ${t.worktree}`)
        else await $.process.run(['git', '-C', repo, 'worktree', 'remove', '--force', t.worktree])
        await save($, { ...t, state: 'done', delivered: 'merge', ...(dirty ? {} : { worktree: undefined }) })
        continue
      }
    }
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
    if (cur.state !== 'watching') continue
    await save($, { ...cur, state, status, every, next: at + every, changes, ...ended })
    if (state !== 'watching' && cur.return) {
      await $.session.send({ to: { sessionId: cur.sender }, text: reportMessage({ ...cur, state, report: status, log: 'none' }, '') })
    }
  }
  await refresh($)
}

/** Host: a task claimed by a host that is no longer the live one is the live host's now: a watch goes on, a worker's task
 * fails (its worker ended with its session) and frees its slot. */
async function orphans($: $) {
  const me = await $.session.id()
  for (const t of await tasks($)) {
    if (!t.host || t.host === me || ENDED.includes(t.state)) continue
    // A watch and a ready task go on under the live host (its merged check reaches the ready one).
    if (t.kind === 'watch' || t.state === 'ready') await save($, { ...t, host: me })
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
  const rules = `${$.plugin.root}/skills/kiss-mini/references/handoff.md`
  const dir = await folder($, id)
  const b = brief(t, rules, dir, await seedFile($, t, dir))
  // The 30 minutes start at the spawn: a slow seed is the host's time, not the worker's. A stop meanwhile stands.
  const seeded = (await $.store.get(TASK + id)) as Task
  if (seeded.stopped || seeded.state !== 'working') return
  await save($, { ...seeded, claimed: await $.clock.now() })
  if (b.isCut) await $.fs.write(`${dir}/task.md`, b.whole)
  const r = await $.agent.spawn({
    subagentType: 'kiss:kiss-worker',
    prompt: b.text,
    description: `kiss-mini ${id}: ${t.title.slice(0, 80)}`,
    cwd: t.worktree ?? t.cwd,
  })
  // The worker's turn.start may have written the task meanwhile: build on the stored entry.
  const now = (await $.store.get(TASK + id)) as Task
  if (r.deny !== undefined) await save($, { ...now, state: 'failed', report: r.deny, finished: await $.clock.now() })
  else if (r.agentId) await save($, { ...now, agentId: r.agentId })
}

/** Whether this session runs KISS installed (from a git or a folder marketplace), not from --plugin-dir: the host must load
 * it the same way, as each way has its own store. A folder marketplace's root is the folder itself, so the root alone
 * cannot tell; the installed list can. A cache root ends in its version, and a session keeps its version's root after an
 * update installs the next: the cache paths match without that last folder. */
// shortcut: a --plugin-dir of the very folder an enabled folder marketplace installs reads as installed; rare, upgrade if met.
async function installed($: $) {
  const up = (path: string) => path.replace(/\/[^/]+\/?$/, '')
  try {
    const r = await $.process.run(['claude', 'plugin', 'list', '--json'])
    const list = JSON.parse(r.stdout) as { enabled?: boolean; installPath?: string; readFromFolder?: string }[]
    return r.exitCode === 0 && list.some(p => p.enabled && ((p.installPath && up(p.installPath) === up($.plugin.root)) || p.readFromFolder === $.plugin.root))
  } catch {
    return false
  }
}

/** Sender: one message to the host (a task, an answer, a stop); a new host when none takes it. */
async function wake($: $, text: string) {
  const host = (await $.store.get(HOST)) as { sessionId: string; beat: number } | undefined
  // A host whose beat (every minute) is 3 minutes old is gone: no send to it.
  const live = host && (await $.clock.now()) - host.beat < HOST_GONE
  if (live && (await $.session.send({ to: { sessionId: host.sessionId }, text })).isDelivered) return 'sent'
  // No prompt: the host's own model never runs. Haiku in case the person attaches and types. The flag rides in
  // --settings: a session started from a background session does not get the caller's environment.
  const settings = JSON.stringify({ env: { KISS_MINI_HOST: '1' } })
  const dir = (await installed($)) ? [] : ['--plugin-dir', $.plugin.root]
  const r = await $.process.run(['claude', '--bg', '--name', HOST_NAME, '--model', 'haiku', ...dir, '--settings', settings])
  return r.exitCode === 0 ? 'started a new host' : `${NO_HOST}: ${`${r.stderr}\n${r.stdout}`.trim().replace(/\s*\n\s*/g, ' · ').slice(0, 300)}`
}

/** A task no host can take ends failed with the reason. */
async function started($: $, t: Task) {
  const how = await wake($, `KISS-MINI task ${t.id}`).catch((err: Error) => `${NO_HOST}: ${err.message}`)
  if (how.startsWith(NO_HOST)) {
    await save($, { ...((await $.store.get(TASK + t.id)) as Task), state: 'failed', report: how, finished: await $.clock.now() })
    await refresh($)
  }
  return how
}

const DELIVERY: [Delivery, string][] = [['merge', 'Merge into the base'], ['push', 'Push'], ['pr', 'Draft PR'], ['discard', 'Discard']]

/** Whether a code task still holds something to discard: its worktree, or a branch no delivery used. */
const holds = (t: Task) => !!t.worktree || (t.state !== 'done' && !!t.branch)

/** Whether the pane offers this delivery: Discard for any code task that still holds a worktree or a branch, the others when
 * an owner's task is ready with its worktree (the harness merges its own tasks). */
const offers = (t: Task, how: Delivery) =>
  isCode(t) && !t.busy && (how === 'discard' ? holds(t) && t.state !== 'working' : t.state === 'ready' && t.brief === undefined && !!t.worktree)

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

/** A code task's own repository (D16): the main checkout of its worktree's git folder, else the sender's folder. */
async function repoOf($: $, t: Task) {
  if (t.repo) return t.repo
  const common = t.worktree ? await $.process.run(['git', '-C', t.worktree, 'rev-parse', '--path-format=absolute', '--git-common-dir'], { timeoutMs: 120_000 }) : undefined
  return common?.exitCode === 0 ? common.stdout.trim().replace(/\/\.git$/, '') : t.cwd
}

async function deliverOnce($: $, id: string, how: Delivery) {
  const t = (await $.store.get(TASK + id)) as Task | undefined
  if (!t || !offers(t, how) || !t.branch) return
  await save($, { ...t, busy: how })
  // What a failure leaves in the ledger: the task as it was, with what this press already did.
  let left = t
  const failed = async (words: string) => {
    await save($, left)
    await refresh($)
    $.ui.toast(`kiss-mini ${id}: ${how} failed: ${words.trim().replace(/\s*\n\s*/g, ' · ').slice(0, 400)}`)
  }
  try {
    const run = (cwd: string, ...args: string[]) => $.process.run(['git', '-C', cwd, ...args], { timeoutMs: 120_000 })
    // Discard runs in the task's own repository, kept on the task, so a press after an interrupt finds it with both
    // folders gone.
    if (how === 'discard' && !t.repo) {
      left = { ...t, repo: await repoOf($, t) }
      await save($, { ...left, busy: how })
    }
    const git = (...args: string[]) => run(how === 'discard' ? left.repo! : t.cwd, ...args)
    let r = { exitCode: 0, stdout: '', stderr: '' }
    let pushed = false
    if (how === 'merge') {
      const head = await git('rev-parse', '--abbrev-ref', 'HEAD')
      const merging = (await git('rev-parse', '-q', '--verify', 'MERGE_HEAD')).exitCode === 0
      const unmerged = (await git('diff', '--name-only', '--diff-filter=U')).stdout.trim()
      // A sender's folder that is gone (or holds no repository): git's own words name it.
      if (head.exitCode !== 0) r = head
      else if (head.stdout.trim() !== t.base) r = { exitCode: 1, stdout: '', stderr: `check out ${t.base} in ${t.cwd} first` }
      else if (merging || unmerged) r = { exitCode: 1, stdout: '', stderr: `a merge is under way in ${t.cwd}: finish or abort it first` }
      // No merge was under way before this one, so a MERGE_HEAD now is this press's own.
      else if ((r = await git('merge', '--no-edit', t.branch)).exitCode !== 0 && (await git('rev-parse', '-q', '--verify', 'MERGE_HEAD')).exitCode === 0) {
        await git('merge', '--abort')
      }
    } else if (how !== 'discard') {
      r = await git('push', '-u', 'origin', t.branch)
      pushed = r.exitCode === 0
      if (pushed && how === 'pr') {
        r = await $.process.run(['gh', 'pr', 'create', '--draft', '--base', t.base!, '--head', t.branch, '--title', t.title, '--body', t.pr ?? t.report ?? ''], { cwd: t.cwd, timeoutMs: 120_000 })
      }
    }
    if (r.exitCode !== 0) return failed(`${how === 'pr' && pushed ? 'pushed; draft PR failed: ' : ''}${[r.stdout, r.stderr].map(x => x.trim()).filter(Boolean).join('\n')}`)
    // The delivered work is the branch (or, for a discard, nothing): the worktree goes, whatever it holds. A worktree
    // git no longer lists (its folder deleted, then pruned) is gone too; only a list that worked says so.
    if (t.worktree) {
      const removed = await git('worktree', 'remove', '--force', t.worktree)
      const list = removed.exitCode === 0 ? removed : await git('worktree', 'list', '--porcelain')
      if (removed.exitCode === 0 || (list.exitCode === 0 && !list.stdout.split('\n').includes(`worktree ${t.worktree}`))) left = { ...left, worktree: undefined }
      else if (how === 'discard') return failed(list.exitCode === 0 ? `worktree kept at ${t.worktree}: ${removed.stderr}` : list.stderr || list.stdout)
      else $.ui.toast(`kiss-mini ${id}: worktree kept at ${t.worktree}: ${removed.stderr.trim().replace(/\s*\n\s*/g, ' · ').slice(0, 200)}`)
    }
    if (how === 'discard') {
      const deleted = await git('branch', '-D', t.branch)
      // A branch an interrupted press already deleted is gone too; only a list that worked says so.
      const list = deleted.exitCode === 0 ? deleted : await git('branch', '--list', t.branch)
      if (deleted.exitCode !== 0 && (list.exitCode !== 0 || list.stdout.trim())) return failed(deleted.stderr || deleted.stdout)
    }
    const { pr, diff, tests, ...rest } = left
    await save($, { ...rest, state: 'done', delivered: how })
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
    await $.tool.register({
      name: 'handoff',
      description:
        'kiss-mini: hand a side task (outside the current tickets) to a background worker. kind: code, bug, question, or watch (with target); ' +
        'brief: in the format of skills/kiss-mini/references/handoff.md, at most 1,500 characters; base: the branch a code ' +
        'or bug task starts from (the harness branch); return: true sends the report back to this session as one message.',
      inputSchema: {
        type: 'object',
        properties: {
          kind: { type: 'string', enum: ['code', 'bug', 'question', 'watch'] },
          target: { type: 'string', description: 'watch only: pr <n>, run <id>, or a test command' },
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
        description: 'kiss-mini workers: report your plan\'s step as you start it: step (1-based) of total steps.',
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

  // /kiss-mini is the skill's own command (kiss:kiss-mini): Claude Code refuses to register the name again, so the mod answers it.
  on('command.run', { command: 'kiss:kiss-mini' }, async ($, e) => {
    // --now: the owner orders the task outright, and the worker skips the three checks.
    const all = e.args.trim().split(/\s+/).filter(Boolean)
    const now = all.includes('--now')
    const [verb = '', ...rest] = all.filter(word => word !== '--now')
    if (verb === '') {
      await $.ui.open({ id: PANE, title: 'kiss-mini' })
      return { text: 'kiss-mini: pane opened.' }
    }
    if (e.args.trim() !== 'status') {
      const id = await newId($)
      const cwd = await $.session.cwd()
      const t: Task = { id, kind: 'question', title: rest.join(' '), sender: await $.session.id(), cwd, state: 'working', started: await $.clock.now(), key: crypto.randomUUID(), ...(now ? { now } : {}) }
      if (verb === 'stop') {
        const known = (await $.store.get(TASK + (rest[0] ?? ''))) as Task | undefined
        if (!known) return { text: `kiss-mini: no task ${rest[0] ?? ''}. /kiss-mini status lists them.` }
        return { text: `kiss-mini ${known.id}: stop asked (${await wake($, `KISS-MINI stop ${known.id} ${known.key}`)}).` }
      }
      if (verb === 'watch') {
        Object.assign(t, { kind: 'watch', state: 'watching', ...watchOf(rest) })
        if (!t.target) return { text: 'kiss-mini: watch pr <number|url>, watch run <id|url>, or watch <test command>.' }
      } else if (verb !== 'ask') {
        const words = [verb, ...rest]
        const at = words.indexOf('--base')
        const base = at >= 0 ? words.splice(at, 2)[1] : undefined
        const head = base ?? (await $.process.run(['git', '-C', cwd, 'rev-parse', '--abbrev-ref', 'HEAD'])).stdout.trim()
        if (!head || head === 'HEAD') return { text: `kiss-mini: ${cwd} is on no branch (or in no repository): name one with --base <branch>.` }
        Object.assign(t, { kind: 'code', title: words.join(' '), base: head, branch: `mini/${id}`, worktree: `${await folder($, id)}/wt` })
      }
      if (!t.title) return { text: 'kiss-mini: say what to do: /kiss-mini <task>, /kiss-mini ask <question>.' }
      await save($, t)
      await refresh($)
      return { text: `kiss-mini ${id}: ${t.kind} started (${await started($, t)}).` }
    }
    const lines = (await tasks($)).map(t => `${t.id} ${t.kind} ${t.state}: ${t.title}${t.report ? ` - ${t.report}` : ''}`)
    return { text: lines.join('\n') || 'kiss-mini: no tasks.' }
    // A throw would let the skill run in the mod's place (a second task): answer the failure instead.
  }).catch(($, e, next) => ({ text: `kiss-mini: failed: ${next.error.message ?? next.error.kind}` }))

  // Any session: the hand-off tool records a task and wakes the host, as /kiss-mini does.
  on('tool.call', { tool: 'mcp__kiss__handoff' }, async ($, e) => {
    const a = e as unknown as { kind: Task['kind']; title: string; brief: string; base?: string; return?: boolean; target?: string }
    if (a.kind === 'watch') {
      const w = watchOf((a.target ?? '').trim().split(/\s+/).filter(Boolean))
      if (!w.target) return { result: 'kiss-mini: a watch needs a target: pr <n>, run <id>, or a test command.' }
      const id = await newId($)
      const t: Task = { id, kind: 'watch', title: a.title || w.target, ...w, return: a.return === true, sender: await $.session.id(), cwd: await $.session.cwd(), state: 'watching', started: await $.clock.now(), key: crypto.randomUUID() }
      await save($, t)
      await refresh($)
      return { result: `kiss-mini task ${id} (watch) started (${await started($, t)}).${t.return ? ' Its end comes back to this session as one message.' : ''}` }
    }
    if (!['code', 'bug', 'question'].includes(a.kind) || !a.title || !a.brief) return { result: 'kiss-mini: kind (code, bug, question or watch), title and brief are needed.' }
    if (a.brief.length > BRIEF_MAX) return { result: `kiss-mini: the brief has ${a.brief.length} characters; at most ${BRIEF_MAX}.` }
    const id = await newId($)
    const cwd = await $.session.cwd()
    const t: Task = { id, kind: a.kind, title: a.title, brief: a.brief, return: a.return === true, sender: await $.session.id(), cwd, state: 'working', started: await $.clock.now(), key: crypto.randomUUID() }
    if (isCode(t)) {
      const base = a.base || (await $.process.run(['git', '-C', cwd, 'rev-parse', '--abbrev-ref', 'HEAD'])).stdout.trim()
      if (!base || base === 'HEAD') return { result: `kiss-mini: ${cwd} is on no branch: give a base.` }
      Object.assign(t, { base, branch: `mini/${id}`, worktree: `${await folder($, id)}/wt` })
    }
    await save($, t)
    await refresh($)
    return { result: `kiss-mini task ${id} (${t.kind}) started (${await started($, t)}).${t.return ? ' Its report comes back to this session as one message.' : ''}` }
  })

  // Host: a worker's progress tool sets its step n of m.
  on('tool.call', { tool: 'mcp__kiss__progress' }, async ($, e) => {
    const a = e as unknown as { step: number; total: number; agentId?: string }
    const t = (await tasks($)).find(x => a.agentId !== undefined && x.agentId === a.agentId)
    if (t) await save($, { ...t, step: a.step, total: a.total })
    return { result: t ? `step ${a.step} of ${a.total} noted` : 'kiss-mini: no task runs in this loop.' }
  })

  // Host: each tool call of a worker is its last tool call; after a new one, at most every 30 s, a small model
  // writes the one-line status from the recent calls.
  on('tool.call', async ($, e, next) => {
    if (e.agentId === undefined || !(await isHost($))) return next(e)
    const t = (await tasks($)).find(x => x.agentId === e.agentId)
    if (t?.stopped) return { deny: `kiss-mini: the owner stopped this task (${t.report}). Make no more tool calls; end now.` }
    if (t && GITHUB_WRITES.test(String(e.tool))) return { deny: 'kiss-mini: only the owner\'s press in the /kiss-mini pane writes to GitHub. Commit on your branch and report.' }
    // A question reads the owner's own working tree: it writes no file there, and its commands leave no caches.
    // shortcut: read-only by rule; only Edit, Write and NotebookEdit are denied and the Python and pytest caches are
    // off, so a Bash command (cargo test, pytest --cov, sed -i, git stash) can still write in the checkout; upgrade:
    // deny write verbs in Bash, or run the question in a copy of the working tree.
    if (t?.kind === 'question' && FILE_TOOLS.includes(String(e.tool))) {
      return { deny: 'kiss-mini: a question changes no file. Answer from what you read.' }
    }
    // D21: a worker's shell starts in the host's folder whatever the spawn's cwd, so each Bash command first goes to the
    // worker's own folder (a question: its checkout); the guard below judges the command as it then runs. D24: a command
    // the worker already started with the prefix stays as it is, as auto mode reviewed it.
    const prefix = t && String(e.tool) === 'Bash' ? bashPrefix(t) : undefined
    const command = String((e as { command?: string }).command ?? '')
    const r = await next(prefix && !command.startsWith(prefix) ? { ...e, command: prefix + command } as typeof e : e)
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
    // Its failure (a session that ended meanwhile) costs only the line.
    if (due) void statusLine($, t.id, fresh.title, calls).catch(() => undefined)
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
    if (verb === 'task') {
      await run($, id)
      await refresh($)
    }
    else if (verb === 'stop' && owner && t && !ENDED.includes(t.state)) await stop($, t, 'stopped')
    else if (verb === 'answer' && owner && t?.agentId && t.state === 'waiting for you' && t.wait !== 'permission') {
      // The same worker takes the answer and goes on: a finished subagent is resumed with the message. The wait does
      // not count toward the 30 minutes.
      await save($, { ...t, state: 'working', notified: false, report: undefined, claimed: await $.clock.now() })
      await $.session.send({ to: { agentId: t.agentId }, text: `The owner answers your question: ${text.trim()}` })
      await refresh($)
    }
    return { consumed: `kiss-mini ${verb} ${id}` }
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
    // An aborted turn with no answer is no report (its host stopped): orphans() ends the task.
    if (!t || t.stopped || (e.isAborted && !e.answer.trim())) return next(e)
    const { state, summary } = parseReport(e.answer, t.kind)
    const log = `${await folder($, t.id)}/report.md`
    await $.fs.write(log, e.answer)
    const fields: Partial<Task> = { state, report: summary, log, finished: await $.clock.now() }
    if (isCode(t)) {
      const stat = await $.process.run(['git', '-C', t.cwd, 'diff', '--shortstat', `${t.base}...${t.branch}`])
      fields.diff = stat.stdout.trim() || 'no change'
      fields.ahead = Number((await $.process.run(['git', '-C', t.cwd, 'rev-list', '--count', `${t.base}..${t.branch}`])).stdout.trim()) || 0
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

  // Host: a code or bug worker's git writes and file writes stay in its worktree; its git reads may look outside. It
  // runs before the push guard, so a command that does both gets one deny that names both rules.
  // shortcut: symlinks are not followed; Bash writes other than git (sed -i, >), git run by a script, xargs or env -C,
  // and a git output path other than --output (format-patch -o) are not caught; a cd in eval text does not carry to
  // the commands after it, and one in a subshell does; upgrade: run the worker in a sandbox that allows writes only in
  // its worktree.
  on('tool.call', { tool: ['Bash', 'Edit', 'Write', 'NotebookEdit'] }, async ($, e, next) => {
    const a = e as unknown as Record<string, unknown>
    if (e.agentId === undefined || !(await isHost($))) return next(e)
    const t = (await tasks($)).find(x => x.agentId === e.agentId)
    if (!t || !isCode(t) || !writesOutside(a, t.worktree)) return next(e)
    const alsoDelivers = String(e.tool) === 'Bash' && delivers(String(a.command))
    return { deny: `${ONLY_WORKTREE}${alsoDelivers ? ", and only the owner's press in the /kiss-mini pane pushes, merges or opens a pull request" : ''}. Commit on your branch and report.` }
  }).catch(($, e, next) =>
    next.called || e.agentId === undefined || !writesOutside(e as unknown as Record<string, unknown>)
      ? next(e)
      : { deny: `${ONLY_WORKTREE}; its guard failed, so it denies every git write and file write of a subagent.` },
  )

  // Host: D8 holds in code, not only in the brief: a worker may not push, merge or open a pull request.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (e.agentId === undefined || !delivers(e.command) || !(await isHost($))) return next(e)
    if (!(await tasks($)).some(t => t.agentId === e.agentId)) return next(e)
    return { deny: 'kiss-mini: only the owner\'s press in the /kiss-mini pane pushes, merges or opens a pull request. Commit on your branch and report.' }
  }).catch(($, e, next) =>
    next.called || e.agentId === undefined || !delivers(e.command) ? next(e) : { deny: 'kiss-mini: its guard failed; no push, merge or pull request from a subagent.' },
  )

  // Host: its model stays idle; a worker's hand-back or any other prompt but the person's own is dropped.
  on('prompt.submit', async ($, e, next) =>
    (await isHost($)) && e.origin.kind !== 'composer' ? { drop: 'kiss-mini host: handled in code' } : next(e),
  )

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    // Mobile draws no Input: there the owner answers from another surface.
    const Input = e.surface === 'mobile' ? undefined : ($.ui.resolve(e) as { Input?: any }).Input
    const all = await read($, ledger)
    const ended = all.filter(t => ENDED.includes(t.state)).sort((a, b) => (b.finished ?? 0) - (a.finished ?? 0))
    // An ended task that still holds a worktree or a branch stays in view until its Discard.
    // Waiting for the owner first, then working, ready, watching; then the ended ones, newest first.
    const open = all.filter(t => !ENDED.includes(t.state)).sort((a, b) => ORDER.indexOf(a.state) - ORDER.indexOf(b.state))
    const list = [...open, ...ended.filter((t, i) => i < SHOW_ENDED || holds(t))]
    const now = await $.clock.now()
    const age = (t: Task) => {
      const s = Math.round(((t.finished ?? now) - t.started) / 1000)
      return s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${Math.round(s / 3600)}h`
    }
    return (
      <Box flexDirection="column">
        {list.length === 0 && <Text dimColor>No kiss-mini tasks.</Text>}
        {list.map(t => (
          <Box flexDirection="column" key={t.id}>
            <Text>{`${t.id} ${t.kind} ${t.state}: ${t.title}${t.step ? ` · step ${t.step} of ${t.total}` : ''} · ${age(t)}`}</Text>
            {t.report && <Text dimColor>{t.report}</Text>}
            {ENDED.includes(t.state) && t.log && <Text dimColor>full text: {t.log}</Text>}
            {t.state === 'working' && !t.host && <Text dimColor>waits for a slot</Text>}
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
    // A task no host has taken yet waits for a slot: it is counted apart from the working ones.
    const queued = list.filter(t => t.state === 'working' && !t.host).length
    const counts = [
      ...ORDER.map(s => [s as string, list.filter(t => t.state === s && (s !== 'working' || t.host)).length] as const),
      ['waiting for a slot', queued] as const,
    ].filter(([, n]) => n > 0)
    if (counts.length === 0) return next(e)
    // Other mods share this slot: theirs is drawn below the counts.
    const below = await next(e).catch(() => undefined)
    const { Box, Button, Text } = $.ui.resolve(e)
    const open = () => $.ui.open({ id: PANE, title: 'kiss-mini' })
    const mine = (
      <Button key="mini-open" plain onPress={open}>
        <Text>kiss-mini: {counts.map(([s, n]) => `${n} ${s}`).join(' · ')}</Text>
      </Button>
    )
    return below ? <Box flexDirection="column">{mine}{below}</Box> : mine
  })
}
