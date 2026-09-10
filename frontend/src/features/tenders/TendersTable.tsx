import { Link } from "@tanstack/react-router"
import { FileSearchIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
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
  statusLabel,
} from "@/features/tenders/format"

/**
 * Six columns of left-aligned grey text read as one undifferentiated block.
 *
 * What separates a column here is its job, so that is what the styling encodes:
 * the title is the only ink-weight text and the only link; the buyer and
 * category are supporting prose; and every figure — value, published, deadline
 * — is right-aligned and tabular, so the numbers form their own vertical edge
 * and the eye can run down them without reading. The header row is quiet: it
 * labels the columns, it does not compete with them.
 */
export function TendersTable({
  tenders,
  isLoading,
}: {
  tenders: TenderSummary[]
  isLoading?: boolean
}) {
  if (isLoading) {
    return (
      <div className="flex flex-col">
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
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FileSearchIcon />
          </EmptyMedia>
          <EmptyTitle>No tenders match your filters</EmptyTitle>
          <EmptyDescription>
            Try a broader search term or clear a filter.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <>
      {/* Below md the table clipped mid-word at the viewport edge and pushed
          value, published and the deadline off-screen with no scroll
          affordance — losing the one field that decides whether a notice is
          worth reading. On a phone each notice is a stacked row instead. */}
      <ul className="flex flex-col md:hidden">
        {tenders.map((tender) => (
          <li key={tender.id} className="border-t first:border-t-0">
            <Link
              to="/app/tenders/$tenderId"
              params={{ tenderId: tender.id }}
              className="flex flex-col gap-1.5 rounded-lg px-2 py-3.5 transition-colors hover:bg-muted/60"
            >
              <span className="text-sm font-medium">{tender.title}</span>
              <span className="text-xs text-muted-foreground">
                {tender.procuring_entity ?? "—"}
              </span>
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                <Badge variant="outline">{tender.source_code}</Badge>
                <span>{categoryLabel(tender.procurement_category)}</span>
                {formatValue(tender.estimated_value, tender.currency) !==
                "—" ? (
                  <span className="tabular-nums">
                    {formatValue(tender.estimated_value, tender.currency)}
                  </span>
                ) : null}
                <Deadline
                  days={tender.days_to_deadline}
                  deadlineAt={tender.deadline_at}
                  className="ml-auto text-xs"
                />
              </span>
            </Link>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-x-auto md:block">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="text-xs font-medium text-muted-foreground">
                Notice
              </TableHead>
              <TableHead className="text-xs font-medium text-muted-foreground">
                Buyer
              </TableHead>
              <TableHead className="text-xs font-medium text-muted-foreground">
                Category
              </TableHead>
              <TableHead className="text-right text-xs font-medium text-muted-foreground">
                Value
              </TableHead>
              <TableHead className="text-right text-xs font-medium text-muted-foreground">
                Published
              </TableHead>
              <TableHead className="text-right text-xs font-medium text-muted-foreground">
                Closes
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tenders.map((tender) => (
              <TableRow key={tender.id}>
                <TableCell className="max-w-sm py-3 align-top whitespace-normal">
                  <Link
                    to="/app/tenders/$tenderId"
                    params={{ tenderId: tender.id }}
                    className="text-sm font-medium text-foreground hover:underline"
                  >
                    <span className="line-clamp-2">{tender.title}</span>
                  </Link>
                  <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <Badge variant="outline">{tender.source_code}</Badge>
                    {tender.country ?? "—"}
                    {tender.status !== "open" ? (
                      <Badge variant="secondary">
                        {statusLabel(tender.status)}
                      </Badge>
                    ) : null}
                  </span>
                </TableCell>

                <TableCell className="max-w-[16rem] py-3 align-top text-sm whitespace-normal text-muted-foreground">
                  <span className="line-clamp-2">
                    {tender.procuring_entity ?? "—"}
                  </span>
                </TableCell>

                <TableCell className="py-3 align-top text-sm text-muted-foreground">
                  {categoryLabel(tender.procurement_category)}
                </TableCell>

                <TableCell className="py-3 text-right align-top text-sm whitespace-nowrap tabular-nums">
                  {formatValue(tender.estimated_value, tender.currency)}
                </TableCell>

                <TableCell className="py-3 text-right align-top text-sm whitespace-nowrap text-muted-foreground tabular-nums">
                  {formatDate(tender.published_at)}
                </TableCell>

                <TableCell className="py-3 text-right align-top text-sm">
                  <Deadline
                    days={tender.days_to_deadline}
                    deadlineAt={tender.deadline_at}
                    muteNormal
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  )
}
