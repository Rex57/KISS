export type State = 'working' | 'waiting for you' | 'ready' | 'watching' | 'done' | 'failed'

/** One ledger entry, kept in `$.store` under `kiss-mini/task/<id>` and shared by every session. */
export type Task = {
  id: string
  kind: 'question'
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
}

declare module 'claude-code' {
  interface PluginState {
    kiss: { mini: Shaped<Task[]> }
  }
}
