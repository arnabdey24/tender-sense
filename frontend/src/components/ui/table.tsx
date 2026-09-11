import * as React from "react"
import { cn } from "cn"

function Table({
  className,
  scroll = true,
  density = "default",
  fixed = false,
  viewport,
  label,
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
   * Fix the column widths instead of letting content decide them.
   *
   * Auto layout sizes each column to its widest cell, so four columns holding
   * the same kind of number come out 93, 86, 137 and 90 wide, and one long
   * error message takes 708 of 1,180 and starves everything beside it. Worse,
   * the widths move when the data does — a column is a different size on the
   * next refresh. Fixed layout means the header decides, once, and a row is
   * the same shape every time it is read.
   *
   * Carries a min-width, because the two together are a trap without it: on a
   * phone the fixed columns already exceed the screen, the table is still
   * `w-full`, and the remainder left for the one flexible column goes
   * negative — so the identity column collapses to nothing and its header
   * label prints on top of the next one. The floor makes the container scroll
   * instead. Override it with a `min-w-*` class for a table with more columns
   * than the default assumes.
   */
  fixed?: boolean
  /**
   * Wrap in a horizontally scrolling container.
   *
   * `overflow-x: auto` forces `overflow-y` to `auto` too, so this container is
   * always a scroll root — which is where a sticky header has to measure from.
   * That is handled below rather than left to the caller: getting it wrong
   * does not make the header un-sticky, it pushes it *down* over the first
   * rows, because sticky clamps the element to at least `top` from its
   * scrollport and a content-height container never scrolls back.
   */
  scroll?: boolean
  /**
   * Cap the height so the rows scroll inside the table instead of the page.
   *
   * A log of twenty-five rows is a thousand pixels: the column labels leave
   * the screen after the fourth one and every row after that is read without
   * them. Bounding the container gives the sticky header something to stick
   * to, and keeps the section heading and its filters in view while the rows
   * move. Any Tailwind max-height class.
   *
   * Requires `label`: a region that scrolls has to be reachable from the
   * keyboard, and a tab stop with no accessible name announces as "group".
   */
  viewport?: string
  /** Names the scrollable region. Required whenever `viewport` is set. */
  label?: string
}) {
  const table = (
    <table
      data-slot="table"
      data-density={density}
      className={cn(
        "w-full caption-bottom text-sm",
        fixed && "table-fixed min-w-[44rem]",
        density === "compact" && "[--row-pad-y:0.3125rem]",
        // No container: the page scrolls, so a sticky header has to clear the
        // 56px app header that is already pinned there.
        !scroll && "[--table-sticky-top:3.5rem]",
        className
      )}
      {...props}
    />
  )

  if (!scroll) return table

  return (
    <div
      data-slot="table-container"
      // A bounded region scrolls, and a region that scrolls has to be
      // operable without a pointer: without the tab stop a keyboard-only
      // operator can reach the buttons inside the rows but never the rows
      // below the fold that hold none.
      {...(viewport
        ? { tabIndex: 0, role: "region" as const, "aria-label": label }
        : {})}
      className={cn(
        // This element is the scrollport, so the header measures from its own
        // top edge, not from the app header's.
        "relative w-full overflow-x-auto [--table-sticky-top:0px]",
        viewport,
        viewport &&
          "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
      )}
    >
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
        // drawn as an inset shadow on the cells instead. The offset comes from
        // whichever ancestor is the scrollport, set by `Table`.
        sticky &&
          "sticky top-[var(--table-sticky-top,3.5rem)] z-20 [&_tr]:border-b-0 [&_th]:bg-surface-sunken [&_th]:shadow-[inset_0_-1px_0_var(--border)]",
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
