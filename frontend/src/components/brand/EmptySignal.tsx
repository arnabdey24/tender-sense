import { cn } from "@/lib/utils"

/**
 * The mark, listening, with nothing caught yet.
 *
 * Empty states were a generic Lucide glyph in a grey rounded square, which
 * belongs to no product. This is the TenderSense mark redrawn on its own
 * geometry — the same arcs, centred on (15,12) at radii 3 / 5.2 / 7.4 — with
 * the notice reduced to an outline and the arcs stepped down in opacity as
 * they travel out. The sensor is on; the page is blank; that is the state.
 *
 * Line art from the brand, not an illustration: it inherits `currentColor`
 * and needs no per-theme variant, exactly like `LogoMark`.
 */
export function EmptySignal({
  size = 44,
  className,
  ...props
}: React.ComponentProps<"svg"> & { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      aria-hidden
      className={cn("shrink-0 text-muted-foreground", className)}
      {...props}
    >
      <g
        stroke="currentColor"
        strokeWidth={1.4}
        strokeLinecap="round"
        fill="none"
      >
        {/* Each arc fainter than the one inside it — the signal travelling
            out and finding nothing to return. */}
        <path d="M16.72 9.54A3 3 0 0 1 16.72 14.46" opacity="0.5" />
        <path d="M17.98 7.74A5.2 5.2 0 0 1 17.98 16.26" opacity="0.32" />
        <path d="M19.25 5.94A7.4 7.4 0 0 1 19.25 18.06" opacity="0.16" />

        {/* The notice as an outline rather than a solid: nothing has arrived
            to fill it in. Rules are dashed for the same reason. */}
        <rect
          x="2.75"
          y="3.75"
          width="11.5"
          height="16.5"
          rx="1.5"
          opacity="0.45"
        />
        <path d="M5.5 9H11.5" opacity="0.3" strokeDasharray="1 2" />
        <path d="M5.5 12.5H11.5" opacity="0.3" strokeDasharray="1 2" />
        <path d="M5.5 16H9" opacity="0.3" strokeDasharray="1 2" />
      </g>
    </svg>
  )
}
