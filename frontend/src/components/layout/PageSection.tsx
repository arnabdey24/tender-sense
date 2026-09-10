import type * as React from "react"

import { cn } from "@/lib/utils"

/**
 * One section grammar for every settings-shaped page.
 *
 * These pages had drifted into four different containers and four different
 * measures — Rules nested cards inside a card, Account ran to ~930px while
 * Settings > Notifications ran to ~1520px on the same route family, and Members
 * and Sources wrapped tables in cards while the tender pool sat bare. Nothing
 * about the content asked for that; it was just whatever each page reached for
 * on the day.
 *
 * The house pattern is the one the tender detail and settings index already
 * use: the heading and its explanation held in a narrow rail, the content
 * beside it, sections separated by a rule rather than boxed. A section that
 * genuinely needs a surface of its own passes `contained` — a form on a raised
 * card — but it is a deliberate exception, not the default.
 */
export function PageSection({
  title,
  caption,
  action,
  contained = false,
  className,
  children,
}: {
  title: string
  caption?: React.ReactNode
  action?: React.ReactNode
  /** Raise the content onto a card. For forms that need to read as one object. */
  contained?: boolean
  className?: string
  children: React.ReactNode
}) {
  return (
    <section
      className={cn(
        "grid gap-x-10 gap-y-4 border-t pt-8 first:border-t-0 first:pt-0 lg:grid-cols-12",
        className
      )}
    >
      <div className="lg:col-span-4">
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-heading text-base font-medium">{title}</h2>
          {action ? <div className="lg:hidden">{action}</div> : null}
        </div>
        {caption ? (
          <p className="mt-1.5 text-pretty text-sm leading-relaxed text-muted-foreground">
            {caption}
          </p>
        ) : null}
        {action ? <div className="mt-3 hidden lg:block">{action}</div> : null}
      </div>

      <div className="min-w-0 lg:col-span-8">
        {contained ? (
          <div className="rounded-xl bg-card p-5 ring-1 ring-foreground/10">
            {children}
          </div>
        ) : (
          children
        )}
      </div>
    </section>
  )
}

/**
 * The measure every settings-shaped page shares, so sibling routes stop
 * disagreeing about how wide the same kind of content is.
 */
export function PageBody({
  className,
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={cn("flex w-full max-w-5xl flex-col gap-8", className)}>
      {children}
    </div>
  )
}
