import { createFileRoute } from "@tanstack/react-router"

import { PageHeader } from "@/components/layout/PageHeader"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {pipeline.isPending
              ? "Loading…"
              : `${pipeline.data?.total ?? 0} in play`}
          </CardTitle>
          <CardDescription>
            Matches recommended as a bid or a hold.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ApiErrorAlert error={pipeline.error} />
          <MatchList
            matches={pipeline.data?.items ?? []}
            isLoading={pipeline.isPending}
            emptyTitle="Nothing in the pipeline"
            emptyDescription="Tenders recommended as a bid or hold will collect here."
          />
        </CardContent>
      </Card>
    </>
  )
}
