import type { Match } from "@/features/matches/api"

/**
 * What a grade letter means, in the words the product should have been using
 * on screen all along.
 *
 * A grade is similarity banded: the matcher blends the company's best-matching
 * capability with the mean of its top few, and the bands cut that number up.
 * Three consequences are worth stating outright, because reading the letter
 * without them invites the wrong conclusion:
 *
 *   - It is a measure of *resemblance*, not of winning. An S is not a
 *     favourite; it is a notice that reads like work this company does.
 *   - It is computed against the capability profile only. Eligibility is a
 *     separate axis, which is why an S can still be "not eligible".
 *   - It is relative to nothing. A pool of all-C grades means the profile is
 *     not finding the work, not that the work is bad.
 */
export const GRADE_MEANINGS = {
  S: "Reads like work you already do — several capabilities match closely.",
  A: "A strong fit on at least one capability, with the rest close behind.",
  B: "Recognisably in your area, but the overlap is partial.",
  C: "Little resemblance to anything in your profile.",
} as const

export type GradeThresholds = { S: number; A: number; B: number }

/** The cut-offs a deployment actually runs, so the legend cannot lie. */
export const DEFAULT_THRESHOLDS: GradeThresholds = { S: 0.78, A: 0.7, B: 0.62 }

/**
 * Read the thresholds off a scored match.
 *
 * They are configurable per deployment and each match records the ones it was
 * graded under, so the legend quotes the row rather than a constant that may
 * have been tuned away from underneath it. Falls back to the defaults when
 * nothing on screen has been scored yet — a legend is most useful on an
 * unfamiliar, and often empty, first screen.
 */
export function thresholdsFrom(
  matches: Pick<Match, "score_breakdown">[]
): GradeThresholds {
  for (const match of matches) {
    const calculation = (match.score_breakdown as Record<string, unknown>)
      ?.calculation as Record<string, unknown> | undefined
    const recorded = calculation?.thresholds as
      | Partial<GradeThresholds>
      | undefined
    if (
      typeof recorded?.S === "number" &&
      typeof recorded?.A === "number" &&
      typeof recorded?.B === "number"
    ) {
      return { S: recorded.S, A: recorded.A, B: recorded.B }
    }
  }
  return DEFAULT_THRESHOLDS
}

/** "78% and above", "70–77%", "62–69%", "below 62%". */
export function bandLabel(
  grade: keyof typeof GRADE_MEANINGS,
  thresholds: GradeThresholds
): string {
  const pct = (value: number) => Math.round(value * 100)
  switch (grade) {
    case "S":
      return `${pct(thresholds.S)}% and above`
    case "A":
      return `${pct(thresholds.A)}–${pct(thresholds.S) - 1}%`
    case "B":
      return `${pct(thresholds.B)}–${pct(thresholds.A) - 1}%`
    case "C":
      return `below ${pct(thresholds.B)}%`
  }
}
