import { Link } from "@tanstack/react-router"
import * as React from "react"

import {
  DataTableRowCheckbox,
  DataTableSelectAll,
  SortableHead,
  useDataTableContext,
  useDataTableKeyboard,
  type SortDirection,
} from "@/components/ui/data-table"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { EmptySignal } from "@/components/brand/EmptySignal"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { TenderSummary } from "@/features/tenders/api"
import { Deadline } from "@/features/tenders/Deadline"
import {
  categoryLabel,
  formatDate,
  formatValue,
  sourceShort,
  statusLabel,
} from "@/features/tenders/format"
import { cn } from "@/lib/utils"

export type TenderSort =
  | "published_at"
  | "deadline_at"
  | "title"
  | "estimated_value"

/**
 * A long list sorted by date is still one undifferentiated run of rows: the
 * reader has to compare "19 days left" against "26 days left" to work out
 * where this week ends. When the table is actually ordered by deadline, the
 * cohorts are drawn as subheads, so the shape of the week is visible without
 * reading a single figure.
 */
function cohortOf(days: number | null | undefined): string {
  if (days === null || days === undefined) return "No deadline"
  if (days < 0) return "Overdue"
  if (days <= 7) return "Closing this week"
  if (days <= 30) return "Closing this month"
  return "Later"
}

/**
 * The shared tender pool.
 *
 * Two things had to change structurally. Both the notice and the buyer wrapped
 * to two lines, independently, so no two rows were the same height and the eye
 * had no baseline to run down — each now clamps to one line and the row gets a
 * single optional meta line beneath, which compact density removes entirely.
 * And `Value` was a real column that was empty on roughly nine rows in ten,
 * spending the best right-hand position on em-dashes; it is now off by default
 * and available from the column menu, while the figure itself rides in the
 * meta line where it is actually legible next to the notice it belongs to.
 */
export function TendersTable({
  tenders,
  isLoading,
  sort,
  descending,
  onSort,
  emptyState,
}: {
  tenders: TenderSummary[]
  isLoading?: boolean
  sort: TenderSort
  descending: boolean
  onSort: (key: TenderSort) => void
  /**
   * What no rows means here. The table cannot tell the difference between a
   * filter that excluded everything and a pool that has never been filled, and
   * the two need opposite answers — one says broaden the search, the other has
   * to offer the pull. The caller knows which, so the caller says.
   */
  emptyState?: React.ReactNode
}) {
  const { isVisible, isSelected, activeId, setActiveId } = useDataTableContext()
  const onKeyDown = useDataTableKeyboard()

  const direction: SortDirection = descending ? "desc" : "asc"
  const head = (key: TenderSort) => ({
    active: sort === key,
    direction,
    onSort: () => onSort(key),
  })

  if (isLoading) {
    return (
      <div className="flex flex-col" aria-busy>
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 border-b py-4">
            <Skeleton className="h-4 flex-1" />
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-24" />
          </div>
        ))}
      </div>
    )
  }

  if (tenders.length === 0) {
    return (
      emptyState ?? (
        <Empty size="compact">
          <EmptyHeader>
            <EmptySignal />
            <EmptyTitle>No notices match these filters</EmptyTitle>
            <EmptyDescription>
              Try a broader search term, or clear one of the filters above.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )
    )
  }

  const showValueColumn = isVisible("value")
  const grouped = sort === "deadline_at"
  const columnCount =
    3 +
    (isVisible("buyer") ? 1 : 0) +
    (isVisible("category") ? 1 : 0) +
    (isVisible("source") ? 1 : 0) +
    (showValueColumn ? 1 : 0) +
    (isVisible("published") ? 1 : 0)

  return (
    <>
      {/* Below md the columns cannot fit without clipping the deadline off the
          right edge — the one field that decides whether a notice is worth
          reading — so a phone gets stacked rows instead of a scrolling table. */}
      <ul className="flex flex-col md:hidden">
        {tenders.map((tender) => {
          const value = formatValue(tender.estimated_value, tender.currency)
          return (
            <li key={tender.id} className="border-t first:border-t-0">
              <Link
                to="/app/tenders/$tenderId"
                params={{ tenderId: tender.id }}
                className="flex flex-col gap-1.5 rounded-lg px-2 py-3.5 transition-colors hover:bg-row-hover"
              >
                <span className="flex items-start justify-between gap-3">
                  <span className="text-sm font-medium">{tender.title}</span>
                  <Deadline
                    days={tender.days_to_deadline}
                    deadlineAt={tender.deadline_at}
                    className="shrink-0 text-xs"
                  />
                </span>
                <span className="text-xs text-muted-foreground">
                  {tender.procuring_entity ?? "Buyer not stated"}
                </span>
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                  <span>{categoryLabel(tender.procurement_category)}</span>
                  <span aria-hidden>·</span>
                  <span>{sourceShort(tender.source_code)}</span>
                  {value !== "—" ? (
                    <>
                      <span aria-hidden>·</span>
                      <span className="tabular-nums text-foreground">{value}</span>
                    </>
                  ) : null}
                  {tender.status !== "open" ? (
                    <>
                      <span aria-hidden>·</span>
                      <span>{statusLabel(tender.status)}</span>
                    </>
                  ) : null}
                </span>
              </Link>
            </li>
          )
        })}
      </ul>

      {/* The key handler sits on the wrapper rather than each row, so one
          listener serves the whole table and rows stay plain markup.

          No `overflow-hidden` on this container, tempting though it is for the
          rounded corners: an overflow ancestor becomes a scroll root and the
          sticky header stops sticking to the page. The header cells round
          their own outer corners instead. */}
      <div
        className="hidden rounded-xl bg-card ring-1 ring-foreground/10 md:block"
        onKeyDown={onKeyDown}
      >
        <Table scroll={false}>
          <TableHeader sticky>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-9 rounded-tl-xl pr-0 pl-3">
                <DataTableSelectAll />
              </TableHead>
              <SortableHead {...head("title")}>Notice</SortableHead>
              {isVisible("buyer") ? <TableHead>Buyer</TableHead> : null}
              {isVisible("category") ? <TableHead>Category</TableHead> : null}
              {isVisible("source") ? <TableHead>Source</TableHead> : null}
              {showValueColumn ? (
                <SortableHead align="end" {...head("estimated_value")}>
                  Value
                </SortableHead>
              ) : null}
              {isVisible("published") ? (
                <SortableHead align="end" {...head("published_at")}>
                  Published
                </SortableHead>
              ) : null}
              <SortableHead
                align="end"
                className="rounded-tr-xl pr-1"
                {...head("deadline_at")}
              >
                Closes
              </SortableHead>
            </TableRow>
          </TableHeader>

          <TableBody>
            {tenders.map((tender, index) => {
              const value = formatValue(tender.estimated_value, tender.currency)
              const cohort = cohortOf(tender.days_to_deadline)
              const startsCohort =
                grouped &&
                (index === 0 ||
                  cohortOf(tenders[index - 1].days_to_deadline) !== cohort)
              // Only in the meta line when it is not already a column of its own.
              const metaValue = !showValueColumn && value !== "—" ? value : null
              const closed = tender.status !== "open"

              return (
                <React.Fragment key={tender.id}>
                {startsCohort ? (
                  <TableRow className="hover:bg-transparent">
                    <TableCell
                      colSpan={columnCount}
                      className="bg-surface-sunken py-1.5 pl-3 text-[11px] font-medium tracking-[0.04em] text-muted-foreground uppercase"
                    >
                      {cohort}
                    </TableCell>
                  </TableRow>
                ) : null}
                <TableRow
                  tabIndex={-1}
                  data-row-id={tender.id}
                  data-selected={isSelected(tender.id) || undefined}
                  data-active={activeId === tender.id || undefined}
                  onFocus={() => setActiveId(tender.id)}
                  className="group/row outline-none"
                >
                  <TableCell className="pr-0 pl-3 align-top">
                    <DataTableRowCheckbox id={tender.id} label={tender.title} />
                  </TableCell>

                  <TableCell className="max-w-md align-top whitespace-normal">
                    <Link
                      to="/app/tenders/$tenderId"
                      params={{ tenderId: tender.id }}
                      className={cn(
                        "block truncate text-sm font-medium text-foreground underline-offset-4 outline-none hover:underline focus-visible:underline",
                        closed && "text-muted-foreground"
                      )}
                      title={tender.title}
                    >
                      {tender.title}
                    </Link>
                    {metaValue || closed ? (
                      <span className="row-meta mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                        {metaValue ? (
                          <span className="tabular-nums">{metaValue}</span>
                        ) : null}
                        {metaValue && closed ? (
                          <span aria-hidden className="text-muted-foreground/50">
                            &middot;
                          </span>
                        ) : null}
                        {closed ? <span>{statusLabel(tender.status)}</span> : null}
                      </span>
                    ) : null}
                  </TableCell>

                  {isVisible("buyer") ? (
                    <TableCell className="max-w-[15rem] align-top text-sm text-muted-foreground">
                      <span
                        className="block truncate"
                        title={tender.procuring_entity ?? undefined}
                      >
                        {tender.procuring_entity ?? "Not stated"}
                      </span>
                    </TableCell>
                  ) : null}

                  {isVisible("category") ? (
                    <TableCell className="align-top text-sm text-muted-foreground">
                      {categoryLabel(tender.procurement_category)}
                    </TableCell>
                  ) : null}

                  {isVisible("source") ? (
                    <TableCell className="align-top text-sm text-muted-foreground">
                      <span className="flex items-baseline gap-1.5">
                        {sourceShort(tender.source_code)}
                        {tender.country ? (
                          /*
                            Full muted, not `/70`. Dimming it measured 3.05:1
                            at 12px — under the 4.5:1 this project holds itself
                            to — and it went unnoticed because almost nothing
                            in the pool carried a country until ADB arrived
                            with two hundred notices across twenty-four of
                            them. Size already makes it the secondary half of
                            this cell; opacity was doing the same job twice and
                            failing a bar doing it. It is also not decoration:
                            country is what an eligibility rule filters on.
                          */
                          <span className="text-xs text-muted-foreground">
                            {tender.country}
                          </span>
                        ) : null}
                      </span>
                    </TableCell>
                  ) : null}

                  {showValueColumn ? (
                    <TableCell className="text-right align-top text-sm tabular-nums">
                      {value}
                    </TableCell>
                  ) : null}

                  {isVisible("published") ? (
                    <TableCell className="text-right align-top text-sm text-muted-foreground tabular-nums">
                      {formatDate(tender.published_at)}
                    </TableCell>
                  ) : null}

                  <TableCell className="pr-3 text-right align-top text-sm">
                    <Deadline
                      days={tender.days_to_deadline}
                      deadlineAt={tender.deadline_at}
                      muteNormal
                    />
                  </TableCell>
                </TableRow>
                </React.Fragment>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </>
  )
}
