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
import {
  categoryLabel,
  deadlineInfo,
  formatDate,
  formatValue,
  statusLabel,
  type DeadlineTone,
} from "@/features/tenders/format"
import { cn } from "@/lib/utils"

const DEADLINE_TONE: Record<DeadlineTone, string> = {
  expired: "text-muted-foreground",
  critical: "text-destructive",
  high: "text-warning",
  normal: "text-foreground",
  none: "text-muted-foreground",
}

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
    <div className="overflow-x-auto">
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
          {tenders.map((tender) => {
            const deadline = deadlineInfo(
              tender.days_to_deadline,
              tender.deadline_at
            )
            return (
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

                <TableCell className="py-3 text-right align-top text-sm tabular-nums whitespace-nowrap">
                  {formatValue(tender.estimated_value, tender.currency)}
                </TableCell>

                <TableCell className="py-3 text-right align-top text-sm tabular-nums whitespace-nowrap text-muted-foreground">
                  {formatDate(tender.published_at)}
                </TableCell>

                <TableCell
                  className={cn(
                    "py-3 text-right align-top text-sm font-medium tabular-nums whitespace-nowrap",
                    DEADLINE_TONE[deadline.tone]
                  )}
                >
                  {deadline.label}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
