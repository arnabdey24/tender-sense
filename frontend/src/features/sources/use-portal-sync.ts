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


/**
 * Start a pull, once, when the pool is empty and nothing else is happening.
 *
 * The case this exists for is a deployment nobody has filled yet: a new
 * organization lands on a dashboard with nothing on it, and the honest next
 * step is the one thing they cannot be expected to know to go and do. So it
 * happens for them.
 *
 * Four guards, and each one is load-bearing:
 *
 * * **Only an empty pool.** A full pool and no matches is a profile or rules
 *   problem; pulling the portals again would change nothing and would spend a
 *   cooldown somebody else may need.
 * * **Once per tab.** A module-level flag rather than component state, so
 *   navigating back to the dashboard, or React remounting it, does not fire a
 *   second time.
 * * **Never while one is running or the cooldown is live.** The server would
 *   refuse anyway; not asking is politer and keeps the toast honest.
 * * **The cooldown is deployment-wide.** Ten people opening an empty dashboard
 *   at nine in the morning produce one pull between them, not ten.
 */
let attemptedThisSession = false

export function useAutoSyncEmptyPool(enabled = true): void {
  const state = useSyncState()
  const sync = useSyncSources()
  const data = state.data

  React.useEffect(() => {
    if (!enabled || attemptedThisSession || !data) return
    if (data.pool_size !== 0) return
    if (data.running || data.retry_after_seconds > 0) return
    if (sync.isPending) return

    attemptedThisSession = true
    sync.mutate()
  }, [enabled, data, sync])
}

/** Test seam: forget that this tab has already tried. */
export function resetAutoSync(): void {
  attemptedThisSession = false
}
