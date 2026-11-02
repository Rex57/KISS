export type Delivery = 'merge' | 'push' | 'pr' | 'discard'

export type State = 'working' | 'waiting for you' | 'ready' | 'watching' | 'done' | 'failed'

/** One ledger entry, kept in `$.store` under `kiss-mini/task/<id>` and shared by every session. */
export type Task = {
  id: string
  kind: 'question' | 'code'
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
