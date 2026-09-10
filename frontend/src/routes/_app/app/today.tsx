import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRightIcon } from "lucide-react"

import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { MatchList } from "@/features/matches/MatchList"
import { useTodayShortlist } from "@/features/matches/api"

export const Route = createFileRoute("/_app/app/today")({
  component: TodayPage,
})

function TodayPage() {
  const shortlist = useTodayShortlist({ page_size: 25 })

  return (
    <>
      <PageHeader
        title="Today"
        description="Strong matches that arrived since yesterday."
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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {shortlist.isPending
              ? "Loading…"
              : `${shortlist.data?.total ?? 0} to look at`}
          </CardTitle>
          <CardDescription>
            Only S and A grades that are not already ruled out — the point of a
            shortlist is that it is short.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ApiErrorAlert error={shortlist.error} />
          <MatchList
            matches={shortlist.data?.items ?? []}
            isLoading={shortlist.isPending}
            emptyTitle="Nothing new today"
            emptyDescription="New strong matches will appear here as tenders are ingested."
          />
        </CardContent>
      </Card>
    </>
  )
}
