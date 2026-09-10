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
      <section className="max-w-4xl">
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
