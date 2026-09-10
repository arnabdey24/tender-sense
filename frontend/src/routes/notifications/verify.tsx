import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"

import {
  ConfirmedPanel,
  PublicNotificationAction,
} from "@/features/notifications/PublicAction"

export const Route = createFileRoute("/notifications/verify")({
  validateSearch: z.object({ token: z.string().optional() }),
  component: VerifyRecipientPage,
})

function VerifyRecipientPage() {
  const { token } = Route.useSearch()
  return (
    <PublicNotificationAction
      token={token}
      path="/api/v1/notifications/verify-recipient"
      title="Confirm this address"
      workingLabel="Confirming…"
      render={(result) => <ConfirmedPanel result={result} />}
    />
  )
}
