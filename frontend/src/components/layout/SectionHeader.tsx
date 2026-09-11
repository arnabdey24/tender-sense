import type * as React from "react"

import { cn } from "@/lib/utils"

/**
 * A section title with an optional action on the same baseline.
 *
 * The dashboard, today, matches and pipeline each rebuilt this pair by hand,
 * and they had drifted: two different heading sizes, two different gaps, and
 * an action that was sometimes a button and sometimes a bare link. One
 * component so a section reads the same wherever it appears.
 */
export function SectionHeader({
  title,
  count,
  action,
  className,
  ...props
}: Omit<React.ComponentProps<"div">, "title"> & {
  title: React.ReactNode
  /** Rendered beside the title, in supporting weight — never as a badge. */
  count?: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <div
      data-slot="section-header"
      className={cn(
        "mb-3 flex items-baseline justify-between gap-3",
        className
      )}
      {...props}
    >
      <h2 className="flex items-baseline gap-2 font-heading text-base font-medium">
        {title}
        {count !== undefined && count !== null ? (
          <span className="text-sm font-normal tabular-nums text-muted-foreground">
            {count}
          </span>
        ) : null}
      </h2>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}
