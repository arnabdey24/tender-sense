import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"

import {
  PublicNotificationAction,
  UnsubscribedPanel,
} from "@/features/notifications/PublicAction"

export const Route = createFileRoute("/notifications/unsubscribe")({
  validateSearch: z.object({ token: z.string().optional() }),
  component: UnsubscribePage,
})

function UnsubscribePage() {
  const { token } = Route.useSearch()
  return (
    <PublicNotificationAction
      token={token}
      path="/api/v1/notifications/unsubscribe"
      title="Unsubscribe"
      workingLabel="Unsubscribing…"
      render={(result) => <UnsubscribedPanel result={result} />}
    />
  )
}
