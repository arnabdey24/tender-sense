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
        `max-w-4xl` left roughly 300px of dead gutter on a 1484px screen while
        the rows inside it truncated their own titles. A list of notices is not
        prose: it is scanned, the deadline and the grade are read together with
        the title, and the measure that suits a paragraph starves a row. It
        takes the width the rest of the workspace takes.
      */}
      <section className="max-w-5xl">
        <div className="mb-3 border-b pb-3">
          <h2 className="font-heading text-base font-medium tabular-nums">
            {pipeline.isPending
              ? "Loading…"
              : `${pipeline.data?.total ?? 0} in play`}
          </h2>
        </div>
        <ApiErrorAlert error={pipeline.error} />
        <MatchList
          matches={pipeline.data?.items ?? []}
          isLoading={pipeline.isPending}
          emptyTitle="Nothing in the pipeline yet"
          emptyDescription="Mark a tender as a bid or a hold and it collects here."
        />
      </section>
    </>
  )
}
