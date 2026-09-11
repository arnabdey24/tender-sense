import type * as React from "react"

import { cn } from "@/lib/utils"

/**
 * The section grammar for the operations console.
 *
 * Not `PageSection`, which is right for settings and wrong here. Settings is
 * read once and changed rarely, so a rail of explanation beside the control
 * earns its 28% of the row. Operations is scanned repeatedly, often while
 * something is wrong, and the same rail then costs a third of the width on
 * every section to repeat what the operator learned the first week — pushing
 * Portals to 1,266px of scrolling and the tender pool past 1,800.
 *
 * So: the heading and its action share one line, the caption is one line
 * beneath it and optional, and the content takes the full width. Density is
 * the feature.
 */
export function ConsoleSection({
  title,
  caption,
  action,
  className,
  children,
}: {
  title: string
  /** One line. If it needs a paragraph, it belongs in the runbook. */
  caption?: React.ReactNode
  action?: React.ReactNode
  className?: string
  children: React.ReactNode
}) {
  return (
    <section
      className={cn(
        "flex flex-col gap-3 border-t pt-6 first:border-t-0 first:pt-0",
        className
      )}
    >
      {/*
        One row, not three.
        
        The first attempt at this moved the caption out of the settings rail and
        onto its own full-width line above the content — which reclaimed a third
        of the width and spent it on height, making four of the six pages worse
        than the grammar it replaced. Height is the scarcer resource here: these
        pages were already scrolling past 1,800px.
        
        So the caption rides beside the heading and truncates. An operator who
        needs the full sentence has the runbook; one scanning for a failure has
        the heading.
      */}
      <div className="flex items-baseline gap-3">
        <h2 className="shrink-0 font-heading text-base font-medium">{title}</h2>
        {caption ? (
          <p className="hidden min-w-0 flex-1 truncate text-sm text-muted-foreground md:block">
            {caption}
          </p>
        ) : (
          <span className="flex-1" />
        )}
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  )
}
