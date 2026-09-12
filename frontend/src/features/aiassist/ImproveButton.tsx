import { SparklesIcon, Undo2Icon } from "lucide-react"
import * as React from "react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { useImproveText, type WritingField } from "@/features/aiassist/api"

/**
 * Rewrite the prose in the field this sits under.
 *
 * Two decisions carry the weight here.
 *
 * **It replaces the text in place and offers an undo, rather than opening a
 * dialog with an accept button.** The field is right there and already
 * editable; a modal would ask the person to evaluate a paragraph out of the
 * context they will read it in. Undo costs one button and one piece of state,
 * and makes trying it free — which is the only way anyone finds out whether
 * it is any good.
 *
 * **It is disabled until there is something to improve.** This rewrites what
 * you wrote; it does not invent a company from an empty box. Offering it on a
 * blank field would promise exactly the thing the button cannot honestly do,
 * and the placeholder already shows what a good answer looks like.
 */
export function ImproveButton({
  field,
  value,
  onChange,
  label = "Improve with AI",
}: {
  field: WritingField
  value: string
  onChange: (next: string) => void
  label?: string
}) {
  const improve = useImproveText()
  const [previous, setPrevious] = React.useState<string | null>(null)
  const [note, setNote] = React.useState("")

  const draft = (value ?? "").trim()
  const tooShort = draft.length < 12

  async function run() {
    setNote("")
    const before = value
    const result = await improve.mutateAsync({ field, text: draft }).catch(() => null)
    if (!result) return
    setPrevious(before)
    setNote(result.note)
    onChange(result.text)
  }

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <Button
        type="button"
        variant="ghost"
        size="xs"
        className="text-muted-foreground"
        disabled={improve.isPending || tooShort}
        onClick={() => void run()}
      >
        {improve.isPending ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <SparklesIcon data-icon="inline-start" />
        )}
        {improve.isPending ? "Rewriting…" : label}
      </Button>

      {previous !== null && !improve.isPending ? (
        <Button
          type="button"
          variant="ghost"
          size="xs"
          className="text-muted-foreground"
          onClick={() => {
            onChange(previous)
            setPrevious(null)
            setNote("")
          }}
        >
          <Undo2Icon data-icon="inline-start" />
          Undo
        </Button>
      ) : null}

      {tooShort && !improve.isPending ? (
        <span className="text-xs text-muted-foreground">
          Write a line or two first — this improves your words, it does not
          invent them.
        </span>
      ) : null}

      {/* The model saying "there was not enough here to work with" is more
          useful than a silently unchanged field. */}
      {note ? <span className="text-xs text-muted-foreground">{note}</span> : null}
    </div>
  )
}
