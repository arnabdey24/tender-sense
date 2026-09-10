import type { Match } from "@/features/matches/api"

/**
 * The narrative shown beside a grade. Templated and model-written explanations
 * share this shape, so a fallback is invisible to the reader.
 */
export type Explanation = {
  summary?: string
  why_matched?: string[]
  gaps?: string[]
  risks?: string[]
  next_step?: string
}

/** Read the structured explanation off a match, whatever produced it. */
export function explanationOf(match: Pick<Match, "explanation">): Explanation {
  return (match.explanation ?? {}) as Explanation
}
