import { Link } from "@tanstack/react-router"
import { CheckIcon, PauseIcon, XIcon } from "lucide-react"
import * as React from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import {
  useClearDecision,
  useDecisionHistory,
  useRecordDecision,
  type Decision,
} from "@/features/decisions/api"
import { useMatch } from "@/features/matches/api"

const OPTIONS: {
  value: Decision
  label: string
  icon: typeof CheckIcon
}[] = [
  { value: "bid", label: "Bid", icon: CheckIcon },
  { value: "hold", label: "Hold", icon: PauseIcon },
  { value: "skip", label: "Skip", icon: XIcon },
]

function formatWhen(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

export function DecisionPanel({ tenderId }: { tenderId: string }) {
  const history = useDecisionHistory(tenderId)
  const record = useRecordDecision(tenderId)
  const clear = useClearDecision(tenderId)
  // Null means this organization has never scored the notice, which is the
  // ordinary state before a capability profile exists. The query is already
  // cached by the panels above this one, so this costs no extra request.
  const match = useMatch(tenderId)
  const [note, setNote] = React.useState("")

  const entries = history.data ?? []
  const current = entries.find((entry) => entry.is_current)
  // Everything before the live one — the trail of changed minds.
  const past = entries.filter((entry) => !entry.is_current)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Your decision</CardTitle>
        <CardDescription>
          Marking a tender as a bid starts its deadline reminders.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/*
          Said here rather than enforced by disabling the buttons.

          Recording a decision on an ungraded notice is legitimate — somebody
          read the tender and knows their own business — and blocking it would
          throw away a real judgement to protect a score nobody asked for. But
          the two panels that normally sit above this one render nothing at
          all when there is no match, so the page silently omitted the reason
          its grade was missing, and a bid recorded here looked like it had
          gone nowhere.
        */}
        {!match.isPending && match.data === null ? (
          <p className="rounded-md bg-surface-sunken p-3 text-sm text-muted-foreground text-pretty">
            This notice has not been graded for your organization yet, so there
            is no fit score or eligibility check beside your decision. You can
            still record one — it appears on the{" "}
            <Link
              to="/app/pipeline"
              className="underline underline-offset-4 hover:text-foreground"
            >
              pipeline
            </Link>{" "}
            either way.{" "}
            <Link
              to="/app/settings/profile"
              className="underline underline-offset-4 hover:text-foreground"
            >
              Finish your capability profile
            </Link>{" "}
            to have it scored.
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {OPTIONS.map((option) => (
            <Button
              key={option.value}
              variant={current?.decision === option.value ? "default" : "outline"}
              size="sm"
              disabled={record.isPending}
              onClick={() =>
                record.mutate(
                  { decision: option.value, note: note.trim() || undefined },
                  { onSuccess: () => setNote("") }
                )
              }
            >
              <option.icon data-icon="inline-start" />
              {option.label}
            </Button>
          ))}
          {current ? (
            <Button
              variant="ghost"
              size="sm"
              disabled={clear.isPending}
              onClick={() => clear.mutate()}
            >
              Withdraw
            </Button>
          ) : null}
        </div>

        <Textarea
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Why? (optional — but this is what your team will read later)"
          aria-label="Decision note"
        />

        {current?.note ? (
          <p className="text-sm text-muted-foreground">
            Current note: {current.note}
          </p>
        ) : null}

        {past.length > 0 ? (
          <div className="flex flex-col gap-1">
            <h3 className="text-xs text-muted-foreground">Earlier decisions</h3>
            <ul className="flex flex-col gap-1 text-sm">
              {past.map((entry) => (
                <li key={entry.id} className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{entry.decision}</Badge>
                  <span className="text-xs text-muted-foreground">
                    {formatWhen(entry.created_at)}
                  </span>
                  {entry.note ? <span>{entry.note}</span> : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
