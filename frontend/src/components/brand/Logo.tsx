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
        <path d="M15.51 9.13A3.5 3.5 0 0 1 15.51 14.87" />
        <path d="M16.94 7.09A6 6 0 0 1 16.94 16.91" />
        {!compact && <path d="M18.38 5.04A8.5 8.5 0 0 1 18.38 18.96" />}
      </g>
      <rect x="2" y="2.5" width="11" height="19" rx="2.6" fill="currentColor" />
      <g
        stroke="var(--logo-paper, var(--background))"
        strokeWidth={compact ? 1.6 : 1.5}
        strokeLinecap="round"
      >
        <path d="M5 7.75H10" />
        <path d="M5 12H10" />
        {!compact && <path d="M5 16.25H8" />}
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
