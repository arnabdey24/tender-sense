import { SparklesIcon } from "lucide-react"
import * as React from "react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { useResearchCompany, type CompanyResearch } from "@/features/aiassist/api"
import { isApiError } from "@/lib/api/errors"

/**
 * Read the company's own website and fill the form in from it.
 *
 * The profile is the single biggest reason a new organization sees an empty
 * dashboard — nothing is scored until it exists — and it is also the least
 * rewarding form in the product: it asks a bidder to describe, in list form,
 * work they have been doing for twenty years. Their website already says all
 * of it.
 *
 * What comes back is a **draft**, and the wording here says so before the
 * button is pressed rather than after. The model is reading marketing copy,
 * marketing copy oversells, and the person reading the result is the only one
 * who knows which parts are true. A draft they correct is honest; a profile
 * silently written for them would quietly re-score their whole tender pool
 * against a guess.
 *
 * Failure is reported inline rather than as a toast, because the thing that
 * needs fixing is the address in the box next to it.
 */
export function AutoSetup({
  url,
  onDraft,
  disabled,
  label = "Auto setup from website",
  hint = "We read your website and fill this in. You can edit everything afterwards.",
}: {
  url: string
  onDraft: (draft: CompanyResearch) => void
  disabled?: boolean
  label?: string
  hint?: string
}) {
  const research = useResearchCompany()
  const [error, setError] = React.useState<string | null>(null)
  const [filled, setFilled] = React.useState<string | null>(null)

  const trimmed = (url ?? "").trim()
  const ready = trimmed.length > 3 && trimmed.includes(".")

  async function run() {
    setError(null)
    setFilled(null)
    try {
      const result = await research.mutateAsync({ url: trimmed })
      onDraft(result.draft)
      setFilled(result.retrieved_url || trimmed)
    } catch (err) {
      setError(
        isApiError(err)
          ? err.message
          : "We could not read that website. Check the address, or fill this in yourself."
      )
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled || research.isPending || !ready}
          onClick={() => void run()}
        >
          {research.isPending ? (
            <Spinner data-icon="inline-start" />
          ) : (
            <SparklesIcon data-icon="inline-start" />
          )}
          {research.isPending ? "Reading your website…" : label}
        </Button>
        {!ready && !research.isPending ? (
          <span className="text-xs text-muted-foreground">
            Enter your website address first.
          </span>
        ) : null}
      </div>

      {research.isPending ? (
        <p className="text-xs text-muted-foreground">
          This takes a few seconds. Nothing is saved until you press save.
        </p>
      ) : null}

      {filled ? (
        /* Naming the page it read matters: a company with three domains needs
           to know which one this came from before trusting the answer. */
        <p className="text-xs text-muted-foreground text-pretty">
          Drafted from{" "}
          <span className="font-medium text-foreground">{filled}</span>. Check
          it over — it is a starting point, not a submission.
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="text-xs text-destructive text-pretty">
          {error}
        </p>
      ) : null}

      {!filled && !error && !research.isPending ? (
        <p className="text-xs text-muted-foreground text-pretty">{hint}</p>
      ) : null}
    </div>
  )
}
