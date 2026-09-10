import * as React from "react"

import type { Source } from "./schemas"

/**
 * The assistant answers in Markdown, and the panel used to print it verbatim —
 * so a reply arrived as `*   **Strategic Fit:** ...` with the asterisks showing.
 * Citations were handled by deleting `[source:id]` outright, which left the
 * space in front of it stranded before the full stop (" .").
 *
 * This renders the small, closed set of Markdown the model actually emits, and
 * turns each citation into a numbered chip pointing at the evidence list rather
 * than throwing the attribution away. Everything is built as React nodes; no
 * model output is ever passed to dangerouslySetInnerHTML.
 */

const CITATION = /\[source:\s*([^\]]+)\]/gi

/** Inline emphasis, code, and citation chips. */
function renderInline(text: string, sources: Source[], keyBase: string) {
  // Pull citations out first so a marker can never be split by emphasis parsing.
  const nodes: React.ReactNode[] = []
  let last = 0
  let match: RegExpExecArray | null
  const re = new RegExp(CITATION)
  let n = 0

  const pushText = (raw: string, k: string) => {
    if (!raw) return
    // **bold**, *italic* / _italic_, `code`
    const parts = raw.split(/(\*\*[^*]+\*\*|`[^`]+`|(?<![*\w])[*_][^*_\n]+[*_])/g)
    parts.forEach((part, i) => {
      if (!part) return
      if (part.startsWith("**") && part.endsWith("**")) {
        nodes.push(
          <strong key={`${k}-b${i}`} className="font-semibold">
            {part.slice(2, -2)}
          </strong>
        )
      } else if (part.startsWith("`") && part.endsWith("`")) {
        nodes.push(
          <code
            key={`${k}-c${i}`}
            className="rounded bg-muted px-1 py-0.5 text-[0.85em]"
          >
            {part.slice(1, -1)}
          </code>
        )
      } else if (
        part.length > 2 &&
        (part.startsWith("*") || part.startsWith("_")) &&
        (part.endsWith("*") || part.endsWith("_"))
      ) {
        nodes.push(<em key={`${k}-i${i}`}>{part.slice(1, -1)}</em>)
      } else {
        nodes.push(part)
      }
    })
  }

  while ((match = re.exec(text)) !== null) {
    // Swallow a single space before the marker so the sentence closes cleanly.
    let before = text.slice(last, match.index)
    if (before.endsWith(" ")) before = before.slice(0, -1)
    pushText(before, `${keyBase}-t${n}`)

    const id = match[1].trim().toLowerCase()
    const index = sources.findIndex((s) => s.id.toLowerCase() === id)
    if (index >= 0) {
      const source = sources[index]
      nodes.push(
        <sup
          key={`${keyBase}-s${n}`}
          title={source.label}
          className="ml-0.5 inline-flex min-w-4 justify-center rounded-full bg-muted px-1 text-[0.65em] leading-4 font-medium text-muted-foreground tabular-nums"
        >
          {index + 1}
        </sup>
      )
    }
    last = match.index + match[0].length
    n += 1
  }
  pushText(text.slice(last), `${keyBase}-tail`)
  return nodes
}

type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "h"; level: number; text: string }

function parseBlocks(src: string): Block[] {
  const blocks: Block[] = []
  for (const raw of src.split("\n")) {
    const line = raw.trimEnd()
    const heading = /^(#{1,4})\s+(.*)$/.exec(line)
    // "- item", "* item", and the model's own "*   item"
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line)
    const numbered = /^\s*(\d+)[.)]\s+(.*)$/.exec(line)
    const prev = blocks[blocks.length - 1]

    if (!line.trim()) {
      if (prev?.kind === "p") blocks.push({ kind: "p", lines: [] })
      continue
    }
    if (heading) {
      blocks.push({ kind: "h", level: heading[1].length, text: heading[2] })
    } else if (bullet) {
      if (prev?.kind === "ul") prev.items.push(bullet[1])
      else blocks.push({ kind: "ul", items: [bullet[1]] })
    } else if (numbered) {
      if (prev?.kind === "ol") prev.items.push(numbered[2])
      else blocks.push({ kind: "ol", items: [numbered[2]] })
    } else if (prev?.kind === "p" && prev.lines.length) {
      prev.lines.push(line)
    } else {
      blocks.push({ kind: "p", lines: [line] })
    }
  }
  return blocks.filter((b) => b.kind !== "p" || b.lines.length > 0)
}

export function RichText({
  text,
  sources = [],
}: {
  text: string
  sources?: Source[]
}) {
  const blocks = React.useMemo(() => parseBlocks(text), [text])

  return (
    <div className="flex flex-col gap-3 text-sm leading-relaxed">
      {blocks.map((block, i) => {
        if (block.kind === "h") {
          return (
            <h4 key={i} className="text-sm font-semibold">
              {renderInline(block.text, sources, `h${i}`)}
            </h4>
          )
        }
        if (block.kind === "ul") {
          return (
            <ul key={i} className="flex list-disc flex-col gap-1.5 pl-5">
              {block.items.map((item, j) => (
                <li key={j} className="pl-0.5">
                  {renderInline(item, sources, `u${i}-${j}`)}
                </li>
              ))}
            </ul>
          )
        }
        if (block.kind === "ol") {
          return (
            <ol key={i} className="flex list-decimal flex-col gap-1.5 pl-5">
              {block.items.map((item, j) => (
                <li key={j} className="pl-0.5">
                  {renderInline(item, sources, `o${i}-${j}`)}
                </li>
              ))}
            </ol>
          )
        }
        return (
          <p key={i} className="text-pretty">
            {renderInline(block.lines.join(" "), sources, `p${i}`)}
          </p>
        )
      })}
    </div>
  )
}
