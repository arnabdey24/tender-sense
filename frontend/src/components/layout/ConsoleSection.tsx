import type { LucideIcon } from "lucide-react"
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
  icon: Icon,
  caption,
  action,
  className,
  children,
}: {
  title: string
  /**
   * A 2D glyph for the subsystem this section reports on.
   *
   * Six sections of identical grey text is a wall an operator has to read to
   * navigate. The icon is the same vocabulary as the sidebar entry that led
   * here, so the page confirms where you are before you have read a word of
   * it. Neutral chip, never a coloured one: the colour on these pages belongs
   * to health, and a decorative tint would compete with the one signal that
   * has to be noticed.
   */
  icon?: LucideIcon
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
      <div className="flex items-center gap-3">
        {Icon ? (
          <span
            aria-hidden
            className="flex size-7 shrink-0 items-center justify-center rounded-md bg-surface-sunken ring-1 ring-foreground/5"
          >
            <Icon className="size-4 text-muted-foreground" strokeWidth={1.75} />
          </span>
        ) : null}
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
