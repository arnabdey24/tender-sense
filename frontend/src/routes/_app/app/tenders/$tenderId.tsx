import { createFileRoute, Link } from "@tanstack/react-router"
import {
  ArrowLeftIcon,
  ExternalLinkIcon,
  MessageCircleIcon,
} from "lucide-react"
import { useAssistant } from "@/features/assistant/context"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { useMatch } from "@/features/matches/api"
import { DecisionPanel } from "@/features/decisions/DecisionPanel"
import { EligibilityList } from "@/features/matches/EligibilityList"
import { explanationOf } from "@/features/matches/explanation"
import { VerdictStrip } from "@/features/matches/verdict"
import { RequirementsList } from "@/features/tenders/RequirementsList"
import { useTender } from "@/features/tenders/api"
import {
  categoryLabel,
  deadlineInfo,
  formatDate,
  formatValue,
  statusLabel,
  type DeadlineTone,
} from "@/features/tenders/format"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/_app/app/tenders/$tenderId")({
  component: TenderDetailPage,
})

const DEADLINE_TONE: Record<DeadlineTone, string> = {
  expired: "text-muted-foreground",
  critical: "text-destructive",
  high: "text-warning",
  normal: "text-foreground",
  none: "text-muted-foreground",
}

/** A titled block separated by a rule, not another nested card. */
function Section({
  title,
  children,
  action,
}: {
  title: string
  children: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <section className="border-t pt-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-heading text-base font-medium">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium tabular-nums">{value}</dd>
    </div>
  )
}

/** Why this tender was graded the way it was. Absent until it is scored. */
function Verdict({ tenderId }: { tenderId: string }) {
  const match = useMatch(tenderId)
  if (match.isPending || !match.data) return null

  const explanation = explanationOf(match.data)
  const sections: [string, string[]][] = [
    ["Why it matches", explanation.why_matched ?? []],
    ["Gaps", explanation.gaps ?? []],
    ["Worth checking", explanation.risks ?? []],
  ]

  return (
    <div className="flex flex-col gap-4 rounded-xl bg-card p-5 ring-1 ring-foreground/10">
      <div className="flex flex-col gap-3">
        <h2 className="font-heading text-base font-medium">Your verdict</h2>
        <VerdictStrip match={match.data} showScore />
      </div>

      {explanation.summary ? (
        <p className="text-pretty text-sm leading-relaxed">
          {explanation.summary}
        </p>
      ) : null}

      {sections.map(([heading, items]) =>
        items.length ? (
          <div key={heading} className="flex flex-col gap-1.5 border-t pt-4">
            <h3 className="text-xs font-medium text-muted-foreground">
              {heading}
            </h3>
            <ul className="flex flex-col gap-1 text-sm">
              {items.map((item) => (
                <li key={item} className="text-pretty">
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ) : null
      )}

      {explanation.next_step ? (
        <p className="border-t pt-4 text-sm font-medium">
          Next: {explanation.next_step}
        </p>
      ) : null}
    </div>
  )
}

function Eligibility({ tenderId }: { tenderId: string }) {
  const match = useMatch(tenderId)
  if (match.isPending || !match.data) return null

  return (
    <div className="rounded-xl bg-card p-5 ring-1 ring-foreground/10">
      <h2 className="mb-3 font-heading text-base font-medium">Eligibility</h2>
      <EligibilityList results={match.data.rule_results ?? []} />
    </div>
  )
}

function TenderDetailPage() {
  const assistant = useAssistant()
  const { tenderId } = Route.useParams()
  const tender = useTender(tenderId)

  const backLink = (
    <Link
      to="/app/tenders"
      className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeftIcon className="size-4" />
      All tenders
    </Link>
  )

  if (tender.isPending) {
    return (
      <div className="flex flex-col gap-6">
        {backLink}
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (tender.error || !tender.data) {
    return (
      <div className="flex flex-col gap-6">
        {backLink}
        <ApiErrorAlert error={tender.error} />
      </div>
    )
  }

  const t = tender.data
  const extraction = t.extraction as
    | { attributes?: Record<string, unknown> }
    | null
    | undefined
  const deadline = deadlineInfo(t.days_to_deadline, t.deadline_at)

  return (
    <div className="flex flex-col gap-6">
      {backLink}

      {/* The notice's own identity, then the clock — the two things that decide
          whether this is worth reading at all. */}
      <header className="flex flex-col gap-3">
        <h1 className="text-pretty font-heading text-2xl leading-tight font-semibold tracking-[-0.019em]">
          {t.title}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t.procuring_entity ?? "Procuring entity not stated"}
        </p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
          <span
            className={cn(
              "font-medium tabular-nums",
              DEADLINE_TONE[deadline.tone]
            )}
          >
            {deadline.label}
          </span>
          <span className="text-muted-foreground">·</span>
          <Badge variant="secondary">{statusLabel(t.status)}</Badge>
          <Badge variant="outline">{t.source_code}</Badge>
          <div className="ml-auto flex items-center gap-2">
            {assistant && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => assistant.openTender(tenderId)}
              >
                <MessageCircleIcon data-icon="inline-start" />
                Discuss this tender
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              render={
                <a href={t.canonical_url} target="_blank" rel="noreferrer" />
              }
              nativeButton={false}
            >
              View on portal
              <ExternalLinkIcon data-icon="inline-end" />
            </Button>
          </div>
        </div>
      </header>

      {/* The notice on the left, the assessment and the decision in a rail that
          stays with you while you read it. */}
      <div className="grid gap-x-10 gap-y-8 lg:grid-cols-12">
        <div className="flex flex-col gap-6 lg:col-span-7 xl:col-span-8">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3">
            <Fact
              label="Category"
              value={categoryLabel(t.procurement_category)}
            />
            <Fact label="Method" value={t.procurement_method ?? "—"} />
            <Fact label="Country" value={t.country ?? "—"} />
            <Fact
              label="Estimated value"
              value={formatValue(t.estimated_value, t.currency)}
            />
            <Fact label="Published" value={formatDate(t.published_at)} />
            <Fact label="Deadline" value={formatDate(t.deadline_at)} />
          </dl>

          {t.summary ? (
            <Section title="Summary">
              <p className="max-w-prose text-pretty text-sm leading-relaxed">
                {t.summary}
              </p>
            </Section>
          ) : null}

          {t.description ? (
            <Section title="Description">
              <p className="max-w-prose text-pretty text-sm leading-relaxed whitespace-pre-wrap">
                {t.description}
              </p>
            </Section>
          ) : null}

          {extraction?.attributes &&
          Object.keys(extraction.attributes).length > 0 ? (
            <Section title="Requirements read from this notice">
              <RequirementsList attributes={extraction.attributes} />
            </Section>
          ) : null}
        </div>

        <aside className="flex flex-col gap-4 lg:col-span-5 xl:col-span-4">
          <div className="flex flex-col gap-4 lg:sticky lg:top-20">
            <Verdict tenderId={tenderId} />
            <Eligibility tenderId={tenderId} />
            <DecisionPanel tenderId={tenderId} />
          </div>
        </aside>
      </div>
    </div>
  )
}
