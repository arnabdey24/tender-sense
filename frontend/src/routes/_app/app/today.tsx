import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRightIcon } from "lucide-react"

import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import {
  MatchList,
  NOTHING_NEW_DESCRIPTION,
} from "@/features/matches/MatchList"
import { useTodayShortlist } from "@/features/matches/api"
import { PortalSyncButton } from "@/features/sources/PortalSync"

export const Route = createFileRoute("/_app/app/today")({
  component: TodayPage,
})

function TodayPage() {
  const shortlist = useTodayShortlist({ page_size: 25 })
  const total = shortlist.data?.total ?? 0

  const items = shortlist.data?.items ?? []
  const strongest = items.filter((m) => m.grade === "S").length
  const soonest = items
    .map((m) => m.tender.days_to_deadline)
    .filter((d): d is number => typeof d === "number" && d >= 0)
    .sort((a, b) => a - b)[0]
  const shape = items.length
    ? [
        strongest ? `${strongest} at S` : null,
        soonest === undefined
          ? null
          : soonest === 0
            ? "one closes today"
            : `soonest closes in ${soonest} day${soonest === 1 ? "" : "s"}`,
      ]
        .filter(Boolean)
        .join(" · ")
    : ""

  return (
    <>
      <PageHeader
        title="Today"
        description="Strong matches that arrived since yesterday. Only S and A grades that are not already ruled out — the point of a shortlist is that it is short."
        actions={
          <>
            {/*
              Sync sits to the left of the navigation deliberately. In a
              right-aligned group the rightmost control reads as the most
              prominent, and on this page that belongs to where the reader is
              going next, not to the plumbing that fills the pool.
            */}
            <PortalSyncButton size="default" variant="outline" />
            <Button
              variant="outline"
              render={<Link to="/app/matches" />}
              nativeButton={false}
            >
              All matches
              <ArrowRightIcon data-icon="inline-end" />
            </Button>
          </>
        }
      />

      {/* The list is the page. Wrapping it in a card put a second border around
          content that already separates itself with rules. */}
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
        {/*
          A count alone says how much, never what kind. Two S grades closing
          this week and eleven A grades a month out are the same number and
          completely different mornings — so the line that opens the page says
          the shape of it, from rows already loaded rather than another
          request.
        */}
        <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b pb-3">
          <h2 className="font-heading text-base font-medium tabular-nums">
            {shortlist.isPending ? "Loading…" : `${total} to look at`}
          </h2>
          {shape ? (
            <p className="text-sm text-muted-foreground">{shape}</p>
          ) : null}
        </div>
        <ApiErrorAlert error={shortlist.error} />
        <MatchList
          matches={shortlist.data?.items ?? []}
          isLoading={shortlist.isPending}
          emptyTitle="Nothing new today"
          emptyDescription={NOTHING_NEW_DESCRIPTION}
        />
      </section>
    </>
  )
}
