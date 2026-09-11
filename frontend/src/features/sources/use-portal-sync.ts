import * as React from "react"

import { countdown } from "@/lib/data/time"
import {
  useSyncSources,
  useSyncState,
  type SyncState,
} from "@/features/sources/api"

/**
 * Tick a server-issued wait down locally.
 *
 * The cooldown is ten minutes. Polling for it would be asking a question whose
 * answer is already known — the server said how long, and a clock can count.
 * Reserving the network for what actually changes (whether a pass is running)
 * is also what lets the button stay honest while the tab is idle.
 */
function useCountdown(seconds: number): number {
  // Reset on a new figure from the server, the way React documents deriving
  // state from a prop: compared during render rather than in an effect, so the
  // count never renders one tick behind the answer it is counting down from.
  const [issued, setIssued] = React.useState(seconds)
  const [left, setLeft] = React.useState(seconds)

  if (issued !== seconds) {
    setIssued(seconds)
    setLeft(seconds)
  }

  React.useEffect(() => {
    if (seconds <= 0) return
    const timer = window.setInterval(
      () => setLeft((value) => (value <= 1 ? 0 : value - 1)),
      1000
    )
    return () => window.clearInterval(timer)
  }, [seconds])

  return left
}

type SyncControl = {
  state: SyncState | undefined
  running: boolean
  waiting: number
  disabled: boolean
  label: string
  press: () => void
}

/**
 * The one place that decides what the sync button says and whether it works,
 * so the copy on the empty state and the copy in settings cannot drift apart.
 */
export function usePortalSync(): SyncControl {
  const state = useSyncState()
  const sync = useSyncSources()
  const waiting = useCountdown(state.data?.retry_after_seconds ?? 0)
  const running = state.data?.running ?? false

  return {
    state: state.data,
    running,
    waiting,
    disabled: sync.isPending || running || waiting > 0 || state.isPending,
    label: running
      ? "Syncing…"
      : waiting > 0
        ? `Again in ${countdown(waiting)}`
        : "Sync now",
    press: () => sync.mutate(),
  }
}
