import {
  CheckCircle2Icon,
  ClockIcon,
  MailPlusIcon,
  SendIcon,
  TrashIcon,
  XCircleIcon,
} from "lucide-react"
import * as React from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { PageSection } from "@/components/layout/PageSection"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import {
  useAddRecipient,
  useRecipients,
  useRemoveRecipient,
  useResendVerification,
  type Recipient,
} from "@/features/notifications/api"

function StatusBadge({ recipient }: { recipient: Recipient }) {
  if (recipient.unsubscribed_at) {
    return (
      <Badge variant="outline">
        <XCircleIcon /> Unsubscribed
      </Badge>
    )
  }
  if (recipient.verified_at) {
    return (
      <Badge variant="success">
        <CheckCircle2Icon /> Confirmed
      </Badge>
    )
  }
  return (
    <Badge variant="warning">
      <ClockIcon /> Awaiting confirmation
    </Badge>
  )
}

export function RecipientsCard({ canEdit }: { canEdit: boolean }) {
  const recipients = useRecipients()
  const addRecipient = useAddRecipient()
  const removeRecipient = useRemoveRecipient()
  const resend = useResendVerification()
  const [email, setEmail] = React.useState("")
  const [name, setName] = React.useState("")

  const onAdd = (event: React.FormEvent) => {
    event.preventDefault()
    if (!email.trim()) return
    addRecipient.mutate(
      { email: email.trim(), name: name.trim() || null },
      {
        onSuccess: () => {
          setEmail("")
          setName("")
        },
      }
    )
  }

  return (
    <PageSection
      title="Who receives these emails"
      caption="An address receives nothing until someone holding it confirms — so nobody can be signed up for your shortlist without knowing."
    >
      <div className="flex flex-col gap-4">
        <ApiErrorAlert error={recipients.error} />

        {recipients.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : recipients.data?.length ? (
          <ul className="flex flex-col gap-2">
            {recipients.data.map((recipient) => (
              <li
                key={recipient.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"
              >
                <div className="min-w-0">
                  <div className="truncate font-medium">{recipient.email}</div>
                  {recipient.name && (
                    <div className="text-xs text-muted-foreground">
                      {recipient.name}
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge recipient={recipient} />
                  {canEdit && !recipient.verified_at && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => resend.mutate(recipient.id)}
                      disabled={resend.isPending}
                    >
                      <SendIcon /> Resend
                    </Button>
                  )}
                  {canEdit && (
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Remove ${recipient.email}`}
                      onClick={() => removeRecipient.mutate(recipient.id)}
                      disabled={removeRecipient.isPending}
                    >
                      <TrashIcon />
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No addresses yet. Without one, matches appear in the app but nothing
            is emailed.
          </p>
        )}

        {canEdit && (
          <form onSubmit={onAdd} className="flex flex-wrap items-end gap-2">
            <div className="flex min-w-52 flex-1 flex-col gap-1">
              <label
                htmlFor="recipient-email"
                className="text-xs text-muted-foreground"
              >
                Email address
              </label>
              <Input
                id="recipient-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="bids@yourcompany.com"
                required
              />
            </div>
            <div className="flex min-w-40 flex-1 flex-col gap-1">
              <label
                htmlFor="recipient-name"
                className="text-xs text-muted-foreground"
              >
                Name (optional)
              </label>
              <Input
                id="recipient-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Bid desk"
              />
            </div>
            <Button type="submit" disabled={addRecipient.isPending}>
              <MailPlusIcon /> Add recipient
            </Button>
          </form>
        )}
      </div>
    </PageSection>
  )
}
