export type Delivery = 'merge' | 'push' | 'pr' | 'discard'

export type State = 'working' | 'waiting for you' | 'ready' | 'watching' | 'done' | 'failed'

/** One ledger entry, kept in `$.store` under `kiss-mini/task/<id>` and shared by every session. */
export type Task = {
  id: string
  kind: 'question' | 'code' | 'bug' | 'watch'
  /** A watch: what it checks, its last status, when it checks next and how far apart, and how many changes it saw. */
  watch?: 'pr' | 'run' | 'test'
  target?: string
  status?: string
  next?: number
  every?: number
  changes?: number
  /** The changes the sender has toasted. */
  seen?: number
  /** A hand-off's own brief (handoff.md's format); absent for the owner's /mini, whose brief is built from the title. */
  brief?: string
  /** True: the report goes back to the sender session as one message. */
  return?: boolean
  title: string
  sender: string
  cwd: string
  state: State
  started: number
  finished?: number
  host?: string
  agentId?: string
  report?: string
  log?: string
  notified?: boolean
  /** A code task: its base branch, its mini/<id> branch and worktree, and what the worker's report said. */
  base?: string
  branch?: string
  worktree?: string
  diff?: string
  tests?: string
  pr?: string
  delivered?: Delivery
  /** A delivery under way, claimed before its first git call: a second press finds it taken. */
  busy?: Delivery
}

declare module 'claude-code' {
  interface PluginState {
    kiss: { mini: Shaped<Task[]> }
  }
}
