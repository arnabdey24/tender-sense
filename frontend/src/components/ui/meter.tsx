import { cn } from "@/lib/utils"

import type { TenderGrade } from "@/features/tenders/GradeBadge"

/**
 * A similarity score, drawn against the grades it has to clear.
 *
 * A plain 0–100 bar is useless here. Real scores land between 3% and 15%,
 * so every row would render the same two-pixel sliver and the meter would
 * discriminate nothing. Drawn against the grade thresholds instead, the
 * emptiness is the information: you can see at a glance that a notice is
 * nowhere near a B, which is exactly what the number is telling you.
 *
 * The figure itself is always rendered beside this, so the meter is
 * `aria-hidden` — a screen reader should hear "8%", not "8% 8%".
 */
const TICKS = [0.62, 0.7, 0.78] as const

const FILL_BY_GRADE: Record<TenderGrade, string> = {
  S: "bg-grade-s",
  A: "bg-grade-a",
  B: "bg-grade-b",
  C: "bg-grade-c",
}

export function Meter({
  value,
  grade,
  className,
  ...props
}: Omit<React.ComponentProps<"div">, "children"> & {
  /** Similarity, 0–1. */
  value: number
  grade: TenderGrade
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100

  return (
    <div
      aria-hidden
      data-slot="meter"
      className={cn(
        "relative h-1.5 w-14 overflow-hidden rounded-full bg-surface-sunken ring-1 ring-foreground/10 ring-inset",
        className
      )}
      {...props}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-[var(--motion-base)] ease-(--motion-ease-out)",
          FILL_BY_GRADE[grade]
        )}
        style={{ width: `${pct}%` }}
      />
      {/* Where B, A and S begin. Without them the fill has no frame of
          reference and the bar is decoration. */}
      {TICKS.map((t) => (
        <span
          key={t}
          className="absolute top-0 h-full w-px bg-foreground/30"
          style={{ left: `${t * 100}%` }}
        />
      ))}
    </div>
  )
}
