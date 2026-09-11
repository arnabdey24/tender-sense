import { cn } from "cn"
import { Loader2Icon } from "lucide-react"

/**
 * A spinner is only worth announcing when nothing else says what is happening.
 *
 * Inside a button that already reads "Syncing…", the default `role="status"`
 * and label made the accessible name "Loading Syncing…" — the same fact twice,
 * in the wrong order, on every control in the app that swaps its icon for a
 * spinner while it works. Pass `label={null}` there and the visible text is
 * left to carry it; keep the default wherever the spinner stands alone.
 */
function Spinner({
  className,
  label = "Loading",
  ...props
}: React.ComponentProps<"svg"> & { label?: string | null }) {
  return (
    <Loader2Icon
      data-slot="spinner"
      {...(label
        ? { role: "status", "aria-label": label }
        : { "aria-hidden": true })}
      className={cn("size-4 animate-spin", className)}
      {...props}
    />
  )
}

export { Spinner }
