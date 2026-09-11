import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

/**
 * How many rows a reader can ask for at once.
 *
 * 15 joins the set and leads it: ten filled about half the height of a desk
 * monitor, which spends a scan on a page that could have shown half again as
 * much. The larger steps stay for someone working through a backlog.
 */
const PAGE_SIZES = [15, 25, 50, 100] as const

/**
 * Where you are in a result set, and how to move.
 *
 * "Page 1 of 6" with a Previous and a Next is the weakest useful version of
 * this: it cannot tell you how many results there are, and it cannot get you
 * to page 5 without four clicks. This states the range and the total, and
 * every page is one click away — the middle collapses to an ellipsis so the
 * control stays the same width whether there are three pages or three hundred.
 */
function pageWindow(page: number, count: number): (number | "gap")[] {
  if (count <= 7) return Array.from({ length: count }, (_, i) => i + 1)

  const out: (number | "gap")[] = [1]
  const from = Math.max(2, page - 1)
  const to = Math.min(count - 1, page + 1)

  if (from > 2) out.push("gap")
  for (let i = from; i <= to; i++) out.push(i)
  if (to < count - 1) out.push("gap")

  out.push(count)
  return out
}

export function Paginator({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
  className,
  noun = "result",
}: {
  page: number
  pageSize: number
  total: number
  onPage: (page: number) => void
  /** Omit to hide the rows-per-page control. */
  onPageSize?: (size: number) => void
  className?: string
  /** Singular; pluralised with a trailing s. */
  noun?: string
}) {
  const count = Math.max(1, Math.ceil(total / pageSize))
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, total)

  return (
    <nav
      aria-label="Pagination"
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 border-t pt-3",
        className
      )}
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <p className="text-sm text-muted-foreground tabular-nums">
        {total === 0 ? (
          `No ${noun}s`
        ) : (
          <>
            <span className="font-medium text-foreground">
              {first.toLocaleString()}–{last.toLocaleString()}
            </span>{" "}
            of {total.toLocaleString()} {noun}
            {total === 1 ? "" : "s"}
          </>
        )}
      </p>

      {onPageSize ? (
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Rows
          <Select
            value={String(pageSize)}
            onValueChange={(value) => onPageSize(Number(value))}
          >
            <SelectTrigger size="sm" className="w-[4.5rem]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAGE_SIZES.map((size) => (
                <SelectItem key={size} value={String(size)}>
                  {size}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
      ) : null}
      </div>

      {count > 1 ? (
        <div className="flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Previous page"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
          >
            <ChevronLeftIcon />
          </Button>

          {pageWindow(page, count).map((entry, i) =>
            entry === "gap" ? (
              <span
                key={`gap-${i}`}
                aria-hidden
                className="px-1 text-sm text-muted-foreground"
              >
                &hellip;
              </span>
            ) : (
              <Button
                key={entry}
                variant={entry === page ? "secondary" : "ghost"}
                size="icon-sm"
                aria-label={`Page ${entry}`}
                aria-current={entry === page ? "page" : undefined}
                className={cn(
                  "tabular-nums",
                  entry === page && "font-semibold"
                )}
                onClick={() => onPage(entry)}
              >
                {entry}
              </Button>
            )
          )}

          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Next page"
            disabled={page >= count}
            onClick={() => onPage(page + 1)}
          >
            <ChevronRightIcon />
          </Button>
        </div>
      ) : null}
    </nav>
  )
}
