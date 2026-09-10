import { cn } from "@/lib/utils"

/**
 * The TenderSense mark: a notice, and the arcs of it being picked up.
 *
 * Both tones come from `currentColor` — the document solid, the arcs at 55% —
 * so the mark inherits whatever colour it is placed in and needs no per-theme
 * variant. Below 28px the third arc and the third rule collapse into grey mush,
 * so the mark is redrawn rather than scaled: `detail="compact"` does that, and
 * `size` picks it automatically.
 */
export type LogoMarkProps = React.ComponentProps<"svg"> & {
  size?: number
  detail?: "full" | "compact"
}

export function LogoMark({
  size = 24,
  detail,
  className,
  ...props
}: LogoMarkProps) {
  const compact = (detail ?? (size < 28 ? "compact" : "full")) === "compact"

  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      role="img"
      aria-label="TenderSense"
      className={cn("shrink-0", className)}
      {...props}
    >
      <g
        data-signal=""
        stroke="currentColor"
        strokeWidth={compact ? 1.9 : 1.7}
        strokeLinecap="round"
        opacity="0.55"
      >
        {/* pathLength normalises the three radii so one dash length draws them
            all evenly when the landing hero animates the signal. */}
        <path pathLength={1} d="M16.72 9.54A3 3 0 0 1 16.72 14.46" />
        <path pathLength={1} d="M17.98 7.74A5.2 5.2 0 0 1 17.98 16.26" />
        {!compact && (
          <path pathLength={1} d="M19.25 5.94A7.4 7.4 0 0 1 19.25 18.06" />
        )}
      </g>
      {/*
        A page, not a handset: 13 × 18 is close to paper's 1:1.4, and the 1.5
        corner radius keeps it from rounding into a phone. The top rule is
        heavier than the rest so it reads as a notice's title line.
      */}
      <rect x="2" y="3" width="13" height="18" rx="1.5" fill="currentColor" />
      <g
        stroke="var(--logo-paper, var(--background))"
        strokeLinecap="round"
      >
        {compact ? (
          <>
            <path d="M5 8.5H12" strokeWidth={2.6} />
            <path d="M5 14H10" strokeWidth={1.9} />
          </>
        ) : (
          <>
            <path d="M5 8H12" strokeWidth={2.2} />
            <path d="M5 12H12" strokeWidth={1.5} />
            <path d="M5 16H9.5" strokeWidth={1.5} />
          </>
        )}
      </g>
    </svg>
  )
}

/** The mark reversed out of a brand tile — avatars, app icons, dense chrome. */
export function LogoTile({
  size = 32,
  className,
  ...props
}: React.ComponentProps<"span"> & { size?: number }) {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground",
        className
      )}
      style={{ width: size, height: size, "--logo-paper": "var(--primary)" } as React.CSSProperties}
      {...props}
    >
      <LogoMark size={Math.round(size * 0.62)} />
    </span>
  )
}

/** Mark plus wordmark. `Sense` takes the brand colour; `Tender` takes the ink. */
export function Logo({
  size = 26,
  showWordmark = true,
  className,
  ...props
}: React.ComponentProps<"span"> & {
  size?: number
  showWordmark?: boolean
}) {
  return (
    <span
      className={cn("inline-flex items-center gap-2.5", className)}
      {...props}
    >
      <LogoMark size={size} className="text-primary" />
      {showWordmark && (
        <span
          className="font-heading font-semibold tracking-[-0.017em]"
          style={{ fontSize: Math.round(size * 0.68) }}
        >
          Tender<span className="text-primary">Sense</span>
        </span>
      )}
    </span>
  )
}
