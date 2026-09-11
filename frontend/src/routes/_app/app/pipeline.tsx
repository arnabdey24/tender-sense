import { createFileRoute } from "@tanstack/react-router"

import { PageHeader } from "@/components/layout/PageHeader"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { MatchList } from "@/features/matches/MatchList"
import { usePipeline } from "@/features/matches/api"

export const Route = createFileRoute("/_app/app/pipeline")({
  component: PipelinePage,
})

function PipelinePage() {
  const pipeline = usePipeline({ page_size: 50 })

  return (
    <>
      <PageHeader
        title="Pipeline"
        description="Everything worth acting on, soonest deadline first."
      />

      {/* The page said what it was three times in 400px — description, card
          header, empty state. The page description says it; the count counts. */}
      {/*
        No artificial measure. `max-w-4xl` left ~300px of dead gutter on a wide
        screen while the rows inside it truncated their own titles — the page
        was narrower than its content needed and wider than it used. A list of
        notices is a dense panel, not prose: it is scanned, the grade and the
        deadline are read together with the title, and the design system's
        65–75ch rule is explicitly for prose, with dense panels free to run
        wider. The width goes to the rows.
      */}
      <section>
        <div className="mb-3 border-b pb-3">
          <h2 className="font-heading text-base font-medium tabular-nums">
            {pipeline.isPending
              ? "Loading…"
              : `${pipeline.data?.total ?? 0} in play`}
          </h2>
        </div>
        <ApiErrorAlert error={pipeline.error} />
        {/*
          Split on the decision, because that is what the page is about.
          A flat run of rows sorted by deadline answers "when", and the
          question a bid manager brings here is "what have we actually
          committed to" — two bids due this month is a different week from
          five things still being weighed. Deadline order survives inside
          each run, so nothing is lost.
        */}
        <MatchList
          matches={pipeline.data?.items ?? []}
          isLoading={pipeline.isPending}
          emptyTitle="Nothing in the pipeline yet"
          emptyDescription="Mark a tender as a bid or a hold and it collects here."
          groups={[
            {
              key: "bid",
              label: "Bidding",
              match: (m) => m.recommendation === "bid",
            },
            {
              key: "hold",
              label: "Still deciding",
              match: (m) => m.recommendation !== "bid",
            },
          ]}
        />
      </section>
    </>
  )
}
