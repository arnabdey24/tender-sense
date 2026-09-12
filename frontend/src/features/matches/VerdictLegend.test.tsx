import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { session } from "@/mocks/fixtures"
import { renderRoute, screen } from "@/test/render"

import { bandLabel, thresholdsFrom, DEFAULT_THRESHOLDS } from "./grades"

/**
 * Every list in the product marks notices S, A, B or C and nothing defined
 * the letters. "Needs checking" had the same gap with a worse failure mode:
 * read as a rejection, it stops somebody bidding on a tender they are
 * probably eligible for.
 */
describe("the grade legend", () => {
  it("quotes the thresholds a match was actually graded under", () => {
    const tuned = thresholdsFrom([
      { score_breakdown: { calculation: { thresholds: { S: 0.9, A: 0.8, B: 0.7 } } } },
    ])

    expect(tuned).toEqual({ S: 0.9, A: 0.8, B: 0.7 })
    expect(bandLabel("S", tuned)).toBe("90% and above")
    expect(bandLabel("A", tuned)).toBe("80–89%")
    expect(bandLabel("C", tuned)).toBe("below 70%")
  })

  it("falls back to the defaults when nothing on screen is scored", () => {
    // The first screen a new organization sees is empty, and that is exactly
    // where a legend earns its place.
    expect(thresholdsFrom([])).toEqual(DEFAULT_THRESHOLDS)
    expect(thresholdsFrom([{ score_breakdown: {} }])).toEqual(DEFAULT_THRESHOLDS)
  })

  it("defines every grade and says what needs checking means", async () => {
    const user = userEvent.setup()
    await renderRoute("/app/matches", { session: session() })

    await user.click(
      await screen.findByRole("button", { name: /what the grades mean/i })
    )

    // The grade is resemblance, not a forecast — the reading the letter invites.
    expect(
      await screen.findByText(/not a probability of winning/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/Reads like work you already do/)).toBeInTheDocument()
    expect(
      screen.getByText(/Little resemblance to anything in your profile/)
    ).toBeInTheDocument()
    expect(screen.getByText(/78% and above/)).toBeInTheDocument()

    expect(screen.getByText(/Not a rejection/)).toBeInTheDocument()
  })
})
