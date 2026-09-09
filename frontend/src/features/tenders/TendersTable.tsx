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
import { DeadlineBadge } from "@/features/tenders/DeadlineBadge"
import type { TenderSummary } from "@/features/tenders/api"
import {
  categoryLabel,
  formatDate,
  formatValue,
  statusLabel,
} from "@/features/tenders/format"

export function TendersTable({
  tenders,
  isLoading,
}: {
  tenders: TenderSummary[]
  isLoading?: boolean
}) {
  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-11 w-full" />
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
          <TableRow>
            <TableHead>Title</TableHead>
            <TableHead>Buyer</TableHead>
            <TableHead>Category</TableHead>
            <TableHead>Value</TableHead>
            <TableHead>Published</TableHead>
            <TableHead>Deadline</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tenders.map((tender) => (
            <TableRow key={tender.id}>
              <TableCell className="max-w-sm">
                <Link
                  to="/app/tenders/$tenderId"
                  params={{ tenderId: tender.id }}
                  className="font-medium text-foreground hover:underline"
                >
                  <span className="line-clamp-2">{tender.title}</span>
                </Link>
                <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Badge variant="outline">{tender.source_code}</Badge>
                  {tender.country ?? "—"}
                  {tender.status !== "open" ? (
                    <Badge variant="secondary">
                      {statusLabel(tender.status)}
                    </Badge>
                  ) : null}
                </span>
              </TableCell>
              <TableCell className="max-w-xs text-muted-foreground">
                <span className="line-clamp-2">
                  {tender.procuring_entity ?? "—"}
                </span>
              </TableCell>
              <TableCell>{categoryLabel(tender.procurement_category)}</TableCell>
              <TableCell className="whitespace-nowrap text-muted-foreground">
                {formatValue(tender.estimated_value, tender.currency)}
              </TableCell>
              <TableCell className="whitespace-nowrap text-muted-foreground">
                {formatDate(tender.published_at)}
              </TableCell>
              <TableCell className="whitespace-nowrap">
                <DeadlineBadge
                  days={tender.days_to_deadline}
                  deadlineAt={tender.deadline_at}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
