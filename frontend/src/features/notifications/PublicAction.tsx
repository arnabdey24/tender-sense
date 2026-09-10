import { CheckCircle2Icon, MailXIcon } from "lucide-react"
import * as React from "react"

import { AuthCard } from "@/components/layout/AuthCard"
import { Spinner } from "@/components/ui/spinner"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import { ApiError, isApiError } from "@/lib/api/errors"

type Result = {
  status: string
  email?: string | null
  organization?: string | null
}

type State =
  | { phase: "working" }
  | { phase: "done"; result: Result }
  | { phase: "failed"; error: ApiError }

const MISSING_TOKEN = new ApiError({
  status: 400,
  code: "invalid_token",
  message: "This link is missing its token. Open it directly from the email.",
})

/**
 * The shared shell for the two links that arrive in an email and carry no
 * session — the person clicking may have no TenderSense account at all.
 */
export function PublicNotificationAction({
  token,
  path,
  title,
  workingLabel,
  render,
}: {
  token?: string
  path:
    | "/api/v1/notifications/verify-recipient"
    | "/api/v1/notifications/unsubscribe"
  title: string
  workingLabel: string
  render: (result: Result) => React.ReactNode
}) {
  const [state, setState] = React.useState<State>(() =>
    token ? { phase: "working" } : { phase: "failed", error: MISSING_TOKEN }
  )
  const started = React.useRef(false)

  React.useEffect(() => {
    if (!token || started.current) return
    started.current = true

    void (async () => {
      try {
        const result = await unwrap(api.POST(path, { body: { token } }))
        setState({ phase: "done", result: result as Result })
      } catch (err) {
        if (!isApiError(err)) throw err
        setState({ phase: "failed", error: err })
      }
    })()
  }, [token, path])

  return (
    <AuthCard title={title}>
      {state.phase === "working" && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner /> {workingLabel}
        </div>
      )}
      {state.phase === "failed" && <ApiErrorAlert error={state.error} />}
      {state.phase === "done" && render(state.result)}
    </AuthCard>
  )
}

export function ConfirmedPanel({ result }: { result: Result }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 font-medium">
        <CheckCircle2Icon className="size-5 text-success" />
        Address confirmed
      </div>
      <p className="text-sm text-muted-foreground">
        {result.email} will now receive tender alerts
        {result.organization ? ` from ${result.organization}` : ""}. Every
        message carries a link to stop them again.
      </p>
    </div>
  )
}

export function UnsubscribedPanel({ result }: { result: Result }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 font-medium">
        <MailXIcon className="size-5" />
        Unsubscribed
      </div>
      <p className="text-sm text-muted-foreground">
        {result.email} will not receive further tender emails. Nothing else is
        needed — you can close this page.
      </p>
    </div>
  )
}
