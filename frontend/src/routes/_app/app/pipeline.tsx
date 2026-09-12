import { createFileRoute, Link } from "@tanstack/react-router"

import { PageHeader } from "@/components/layout/PageHeader"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { DecisionList } from "@/features/decisions/DecisionList"
import { useDecisions } from "@/features/decisions/api"

export const Route = createFileRoute("/_app/app/pipeline")({
  component: PipelinePage,
})

/**
 * What this company decided, not what the matcher suggested.
 *
 * The page used to read `/pipeline`, which returns matches the *model*
 * recommends bidding or holding. That made it a saved filter over Matches —
 * on a pool where nothing was graded C it returned the identical set, and the
 * two tabs showed the same nine rows. Worse, it meant the Bid button on every
 * match row wrote to a table no screen in the product ever read: a recorded
 * bid appeared nowhere, and the only way to see one was to reopen the notice
 * you had recorded it on.
 *
 * `/decisions` is the list that was always meant to be here — the schema for
 * its rows still says "enough of the notice to render a pipeline row". A
 * decision belongs to a tender rather than to a match, so this page also shows
 * the ones taken before the profile was finished, which have no grade to show.
 */
function PipelinePage() {
  const decisions = useDecisions()
  const entries = decisions.data?.items ?? []

  // Skips are decisions too, and they are the ones nobody needs to look at.
  // The pipeline is what is still live.
  const live = entries.filter((entry) => entry.decision !== "skip")
  const skipped = entries.length - live.length

  return (
    <>
      <PageHeader
        title="Pipeline"
        description="What your team has committed to, soonest deadline first."
      />

      <section>
        <div className="mb-3 flex flex-wrap items-baseline gap-x-2 border-b pb-3">
          <h2 className="font-heading text-base font-medium tabular-nums">
            {decisions.isPending ? "Loading…" : `${live.length} in play`}
          </h2>
          {skipped > 0 ? (
            <p className="text-sm text-muted-foreground tabular-nums">
              · {skipped} skipped, not shown
            </p>
          ) : null}
        </div>

        <ApiErrorAlert error={decisions.error} />

        <DecisionList
          entries={live}
          isLoading={decisions.isPending}
          emptyTitle="Nothing in the pipeline yet"
          emptyDescription="Mark a tender as a bid or a hold and it collects here."
          groups={[
            {
              key: "bid",
              label: "Bidding",
              match: (entry) => entry.decision === "bid",
            },
            {
              key: "hold",
              label: "Still deciding",
              match: (entry) => entry.decision === "hold",
            },
          ]}
        />

        {!decisions.isPending && live.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            The graded shortlist is on{" "}
            <Link
              to="/app/matches"
              className="underline underline-offset-4 hover:text-foreground"
            >
              Matches
            </Link>
            .
          </p>
        ) : null}
      </section>
    </>
  )
}
