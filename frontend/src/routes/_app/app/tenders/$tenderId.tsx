import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowLeftIcon, ExternalLinkIcon } from "lucide-react"

import { PageHeader } from "@/components/layout/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { DeadlineBadge } from "@/features/tenders/DeadlineBadge"
import { useMatch } from "@/features/matches/api"
import { DecisionPanel } from "@/features/decisions/DecisionPanel"
import { EligibilityList } from "@/features/matches/EligibilityList"
import { explanationOf } from "@/features/matches/explanation"
import { VerdictStrip } from "@/features/matches/verdict"
import { useTender } from "@/features/tenders/api"
import {
  categoryLabel,
  formatDate,
  formatValue,
  statusLabel,
} from "@/features/tenders/format"

export const Route = createFileRoute("/_app/app/tenders/$tenderId")({
  component: TenderDetailPage,
})

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium">{value}</dd>
    </div>
  )
}

/** Why this tender was graded the way it was. Absent until it is scored. */
function VerdictCard({ tenderId }: { tenderId: string }) {
  const match = useMatch(tenderId)
  if (match.isPending || !match.data) return null

  const explanation = explanationOf(match.data)
  const sections: [string, string[]][] = [
    ["Why it matches", explanation.why_matched ?? []],
    ["Gaps", explanation.gaps ?? []],
    ["Worth checking", explanation.risks ?? []],
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Your verdict</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <VerdictStrip match={match.data} showScore />

        {explanation.summary ? (
          <p className="text-sm">{explanation.summary}</p>
        ) : null}

        {sections.map(([heading, items]) =>
          items.length ? (
            <div key={heading} className="flex flex-col gap-1">
              <h3 className="text-xs text-muted-foreground">{heading}</h3>
              <ul className="list-disc pl-5 text-sm">
                {items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null
        )}

        {explanation.next_step ? (
          <p className="text-sm font-medium">Next: {explanation.next_step}</p>
        ) : null}
      </CardContent>
    </Card>
  )
}

/** Rule-by-rule eligibility, with the quote behind each claim. */
function EligibilityCard({ tenderId }: { tenderId: string }) {
  const match = useMatch(tenderId)
  if (match.isPending || !match.data) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Eligibility</CardTitle>
      </CardHeader>
      <CardContent>
        <EligibilityList results={match.data.rule_results ?? []} />
      </CardContent>
    </Card>
  )
}

function TenderDetailPage() {
  const { tenderId } = Route.useParams()
  const tender = useTender(tenderId)

  const backButton = (
    <Button
      variant="outline"
      render={<Link to="/app/tenders" />}
      nativeButton={false}
    >
      <ArrowLeftIcon data-icon="inline-start" />
      All tenders
    </Button>
  )

  if (tender.isPending) {
    return (
      <>
        <PageHeader title="Tender" actions={backButton} />
        <Skeleton className="h-64 w-full" />
      </>
    )
  }

  if (tender.error || !tender.data) {
    return (
      <>
        <PageHeader title="Tender" actions={backButton} />
        <ApiErrorAlert error={tender.error} />
      </>
    )
  }

  const t = tender.data
  const extraction = t.extraction as
    | { attributes?: Record<string, unknown> }
    | null
    | undefined

  return (
    <>
      <PageHeader
        title={t.title}
        description={t.procuring_entity ?? undefined}
        actions={backButton}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{t.source_code}</Badge>
        <Badge variant="secondary">{statusLabel(t.status)}</Badge>
        <DeadlineBadge days={t.days_to_deadline} deadlineAt={t.deadline_at} />
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

      <VerdictCard tenderId={tenderId} />

      <EligibilityCard tenderId={tenderId} />

      <DecisionPanel tenderId={tenderId} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Overview</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Fact label="Category" value={categoryLabel(t.procurement_category)} />
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
            <div className="flex flex-col gap-1">
              <h3 className="text-xs text-muted-foreground">Summary</h3>
              <p className="text-sm">{t.summary}</p>
            </div>
          ) : null}

          {t.description ? (
            <div className="flex flex-col gap-1">
              <h3 className="text-xs text-muted-foreground">Description</h3>
              <p className="text-sm whitespace-pre-wrap">{t.description}</p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {extraction?.attributes &&
      Object.keys(extraction.attributes).length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Extracted requirements</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
              {JSON.stringify(extraction.attributes, null, 2)}
            </pre>
          </CardContent>
        </Card>
      ) : null}
    </>
  )
}
