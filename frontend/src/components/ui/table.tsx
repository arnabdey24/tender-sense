import * as React from "react"
import { cn } from "cn"

function Table({
  className,
  scroll = true,
  density = "default",
  ...props
}: React.ComponentProps<"table"> & {
  /**
   * How much air a row gets.
   *
   * `compact` is for a console: an operator scanning for the one abnormal row
   * wants more rows in view, and the reading distance is a desk rather than a
   * phone. `default` stays for surfaces a customer reads.
   */
  density?: "default" | "compact"
  /**
   * Wrap in a horizontally scrolling container. Opt out when the columns are
   * designed to fit: `overflow-x: auto` forces `overflow-y` to `auto` too,
   * which makes the container a scroll root and stops a sticky header from
   * ever sticking to the page.
   */
  scroll?: boolean
}) {
  const table = (
    <table
      data-slot="table"
      data-density={density}
      className={cn(
        "w-full caption-bottom text-sm",
        density === "compact" && "[--row-pad-y:0.3125rem]",
        className
      )}
      {...props}
    />
  )

  if (!scroll) return table

  return (
    <div data-slot="table-container" className="relative w-full overflow-x-auto">
      {table}
    </div>
  )
}

function TableHeader({
  className,
  sticky = false,
  ...props
}: React.ComponentProps<"thead"> & {
  /** Holds the column labels against the app header while the body scrolls. */
  sticky?: boolean
}) {
  return (
    <thead
      data-slot="table-header"
      data-sticky={sticky || undefined}
      className={cn(
        "[&_tr]:border-b",
        // A collapsed border vanishes under a sticky row, so the hairline is
        // drawn as an inset shadow on the cells instead. `top-14` is the app
        // header's 56px.
        sticky &&
          "sticky top-14 z-20 [&_tr]:border-b-0 [&_th]:bg-surface-sunken [&_th]:shadow-[inset_0_-1px_0_var(--border)]",
        className
      )}
      {...props}
    />
  )
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        // Row states are their own tokens rather than opacity maths on muted,
        // so a row still reads as hovered when it sits on a sunken surface.
        "border-b transition-colors duration-[var(--motion-fast)] hover:bg-row-hover has-aria-expanded:bg-row-hover data-selected:bg-row-selected data-[state=selected]:bg-row-selected",
        "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring data-active:bg-row-hover",
        className
      )}
      {...props}
    />
  )
}

function TableHead({
  className,
  numeric = false,
  ...props
}: React.ComponentProps<"th"> & {
  /** A column of figures: right-aligned, so the digits line up to be compared. */
  numeric?: boolean
}) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "group/head h-9 px-2 text-left align-middle text-[11px] font-medium tracking-[0.04em] uppercase whitespace-nowrap text-muted-foreground [&:has([role=checkbox])]:pr-0",
        numeric && "text-right",
        className
      )}
      {...props}
    />
  )
}

function TableCell({
  className,
  numeric = false,
  ...props
}: React.ComponentProps<"td"> & {
  /**
   * A figure rather than a word.
   *
   * Right-aligned and tabular together, because either alone fails: ragged
   * digits cannot be compared down a column, and proportional figures shift
   * the column every time a count crosses a power of ten.
   */
  numeric?: boolean
}) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        // Vertical padding comes from the density variable on the surface
        // above, so switching density is one attribute flip, not a re-render
        // of class strings on every cell.
        "px-2 py-[var(--row-pad-y,0.5rem)] align-middle whitespace-nowrap [&:has([role=checkbox])]:pr-0",
        numeric && "text-right tabular-nums",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
