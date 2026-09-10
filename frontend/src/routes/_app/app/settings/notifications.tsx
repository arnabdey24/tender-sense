import { createFileRoute } from "@tanstack/react-router"
import { SendIcon } from "lucide-react"
import * as React from "react"

import { PageHeader } from "@/components/layout/PageHeader"
import { StringCombobox } from "@/components/form/StringCombobox"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { RecipientsCard } from "@/features/notifications/RecipientsCard"
import {
  useNotificationSettings,
  useSendTestEmail,
  useUpdateNotificationSettings,
  type NotificationSettings,
} from "@/features/notifications/api"
import { TenderFilterSelect } from "@/features/tenders/TenderFilterSelect"
import { useIsOrgAdmin } from "@/lib/auth/store"
import { timezoneOptions } from "@/lib/data/locale"

export const Route = createFileRoute("/_app/app/settings/notifications")({
  component: NotificationSettingsPage,
})

const GRADE_OPTIONS = [
  { value: "S", label: "S — only the strongest" },
  { value: "A", label: "A and above" },
  { value: "B", label: "B and above" },
  { value: "C", label: "Everything scored" },
]

/** Offsets people actually pick, in days before the deadline. */
const REMINDER_CHOICES = [14, 7, 3, 2, 1]

function Row({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 border-b py-4 last:border-b-0 last:pb-0">
      <div className="max-w-md">
        <div className="font-medium">{title}</div>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="min-w-52">{children}</div>
    </div>
  )
}

function SettingsForm({
  settings,
  canEdit,
}: {
  settings: NotificationSettings
  canEdit: boolean
}) {
  const update = useUpdateNotificationSettings()
  const timezones = React.useMemo(() => timezoneOptions(), [])
  const offsets = settings.reminder_offsets ?? []

  const patch = (body: Parameters<typeof update.mutate>[0]) => {
    if (!canEdit) return
    update.mutate(body)
  }

  const toggleOffset = (days: number) => {
    const next = offsets.includes(days)
      ? offsets.filter((value) => value !== days)
      : [...offsets, days]
    patch({ reminder_offsets: next })
  }

  return (
    <div className="flex flex-col">
      <Row
        title="In-app notifications"
        description="The bell in the header. Costs nothing and needs no email address."
      >
        <Switch
          checked={settings.inapp_enabled}
          onCheckedChange={(checked: boolean) =>
            patch({ inapp_enabled: checked })
          }
          disabled={!canEdit}
          aria-label="In-app notifications"
        />
      </Row>

      <Row
        title="Instant alerts"
        description="Emailed as soon as a match is scored. Worth interrupting someone for — which is why the bar is high by default."
      >
        <Switch
          checked={settings.instant_enabled}
          onCheckedChange={(checked: boolean) =>
            patch({ instant_enabled: checked })
          }
          disabled={!canEdit}
          aria-label="Instant alerts"
        />
      </Row>

      {settings.instant_enabled && (
        <>
          <Row
            title="Alert me from this grade up"
            description="Lower it and alerts stop meaning “drop what you are doing”."
          >
            <TenderFilterSelect
              label="Instant alert grade"
              value={settings.instant_min_grade}
              options={GRADE_OPTIONS}
              onChange={(value) => value && patch({ instant_min_grade: value })}
              anyLabel="S — only the strongest"
            />
          </Row>
          <Row
            title="Only when we are eligible"
            description="Telling you to drop everything for a tender you cannot legally bid on is worse than saying nothing."
          >
            <Switch
              checked={settings.instant_requires_eligible}
              onCheckedChange={(checked: boolean) =>
                patch({ instant_requires_eligible: checked })
              }
              disabled={!canEdit}
              aria-label="Instant alerts only when eligible"
            />
          </Row>
        </>
      )}

      <Row
        title="Daily shortlist"
        description="One email a morning with everything new. Nothing is sent on a day with nothing to report."
      >
        <Switch
          checked={settings.digest_enabled}
          onCheckedChange={(checked: boolean) =>
            patch({ digest_enabled: checked })
          }
          disabled={!canEdit}
          aria-label="Daily shortlist"
        />
      </Row>

      {settings.digest_enabled && (
        <>
          <Row
            title="Send it at"
            description="Your local time, so it lands in your morning rather than the server's."
          >
            <div className="flex flex-col gap-2">
              <Input
                type="time"
                value={(settings.digest_time ?? "08:00:00").slice(0, 5)}
                onChange={(event) =>
                  patch({ digest_time: `${event.target.value}:00` })
                }
                disabled={!canEdit}
                aria-label="Digest send time"
              />
              <StringCombobox
                items={timezones}
                value={settings.digest_timezone}
                onValueChange={(value: string) =>
                  value && patch({ digest_timezone: value })
                }
                placeholder="Select a timezone"
                emptyText="No timezone found."
                aria-label="Digest timezone"
              />
            </div>
          </Row>
          <Row
            title="Include matches from this grade up"
            description="Weaker matches are still counted, just not featured."
          >
            <TenderFilterSelect
              label="Digest grade"
              value={settings.digest_min_grade}
              options={GRADE_OPTIONS}
              onChange={(value) => value && patch({ digest_min_grade: value })}
              anyLabel="B and above"
            />
          </Row>
        </>
      )}

      <Row
        title="Deadline reminders"
        description="Only for tenders you marked as a bid. A reminder about something nobody committed to is an interruption."
      >
        <Switch
          checked={settings.reminders_enabled}
          onCheckedChange={(checked: boolean) =>
            patch({ reminders_enabled: checked })
          }
          disabled={!canEdit}
          aria-label="Deadline reminders"
        />
      </Row>

      {settings.reminders_enabled && (
        <Row
          title="Remind me this far ahead"
          description="Each one is sent once per tender."
        >
          <div className="flex flex-wrap gap-2">
            {REMINDER_CHOICES.map((days) => (
              <Button
                key={days}
                size="sm"
                variant={offsets.includes(days) ? "secondary" : "outline"}
                onClick={() => toggleOffset(days)}
                disabled={!canEdit}
                aria-pressed={offsets.includes(days)}
              >
                {days}d
              </Button>
            ))}
          </div>
        </Row>
      )}
    </div>
  )
}

function NotificationSettingsPage() {
  const isAdmin = useIsOrgAdmin()
  const settings = useNotificationSettings()
  const testEmail = useSendTestEmail()

  return (
    <>
      <PageHeader
        title="Notifications"
        description="What TenderSense tells you about, when, and where it lands."
      />

      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Delivery</CardTitle>
            <CardDescription>
              {isAdmin
                ? "Changes save as you make them."
                : "Ask an admin to change these."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ApiErrorAlert error={settings.error} />
            {settings.isPending ? (
              <div className="flex flex-col gap-3">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : settings.data ? (
              <SettingsForm settings={settings.data} canEdit={isAdmin} />
            ) : null}
          </CardContent>
        </Card>

        <RecipientsCard canEdit={isAdmin} />

        {isAdmin && (
          <Card>
            <CardHeader>
              <CardTitle>Check delivery</CardTitle>
              <CardDescription>
                Prove mail arrives before the first real alert depends on it. A
                shortlist nobody sees is the same as no shortlist.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                variant="outline"
                onClick={() => testEmail.mutate()}
                disabled={testEmail.isPending}
              >
                <SendIcon /> Send myself a test message
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  )
}
