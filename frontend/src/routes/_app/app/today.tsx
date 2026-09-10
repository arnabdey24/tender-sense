import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRightIcon } from "lucide-react"

import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { MatchList } from "@/features/matches/MatchList"
import { useTodayShortlist } from "@/features/matches/api"

export const Route = createFileRoute("/_app/app/today")({
  component: TodayPage,
})

function TodayPage() {
  const shortlist = useTodayShortlist({ page_size: 25 })
  const total = shortlist.data?.total ?? 0

  return (
    <>
      <PageHeader
        title="Today"
        description="Strong matches that arrived since yesterday. Only S and A grades that are not already ruled out — the point of a shortlist is that it is short."
        actions={
          <Button
            variant="outline"
            render={<Link to="/app/matches" />}
            nativeButton={false}
          >
            All matches
            <ArrowRightIcon data-icon="inline-end" />
          </Button>
        }
      />

      {/* The list is the page. Wrapping it in a card put a second border around
          content that already separates itself with rules. */}
      <section className="max-w-4xl">
        <div className="mb-3 flex items-baseline gap-2 border-b pb-3">
          <h2 className="font-heading text-base font-medium tabular-nums">
            {shortlist.isPending ? "Loading…" : `${total} to look at`}
          </h2>
        </div>
        <ApiErrorAlert error={shortlist.error} />
        <MatchList
          matches={shortlist.data?.items ?? []}
          isLoading={shortlist.isPending}
          emptyTitle="Nothing new today"
          emptyDescription="New strong matches will appear here as tenders are ingested."
        />
      </section>
    </>
  )
}
