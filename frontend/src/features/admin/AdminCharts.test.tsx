import { describe, expect, it } from "vitest"

import { PoolIntakeChart, JobOutcomeChart, SpendChart } from "./AdminCharts"
import { render, screen } from "@/test/render"
import type { Trends } from "@/features/admin/api"

/**
 * What these pin is the reading, not the rectangles.
 *
 * jsdom has no layout, so Recharts draws nothing measurable and asserting on
 * bars would test the mock rather than the chart. The part that has to be right
 * regardless of pixels is the sentence a screen reader gets and the sentence
 * shown when there is nothing to draw — which is also the part a sighted
 * reviewer never checks.
 */

function trends(overrides: Partial<Trends> = {}): Trends {
  return {
    days: 3,
    sources: ["adb", "wb"],
    source_names: { adb: "ADB procurement notices", wb: "World Bank" },
    intake: [
      { day: "2026-09-09", by_source: { adb: 0, wb: 12 } },
      { day: "2026-09-10", by_source: { adb: 0, wb: 8 } },
      { day: "2026-09-11", by_source: { adb: 200, wb: 0 } },
    ],
    jobs: [
      { day: "2026-09-09", succeeded: 10, failed: 0, partial: 0 },
      { day: "2026-09-10", succeeded: 8, failed: 2, partial: 1 },
      { day: "2026-09-11", succeeded: 30, failed: 5, partial: 0 },
    ],
    ...overrides,
  }
}

describe("PoolIntakeChart", () => {
  it("names the figure so it is not an unlabelled graphic", () => {
    render(<PoolIntakeChart trends={trends()} />)
    expect(screen.getByRole("figure", { name: /arrivals/i })).toBeInTheDocument()
  })

  it("states the total and each portal's day in words", () => {
    render(<PoolIntakeChart trends={trends()} />)
    const summary = screen.getByRole("figure", { name: /arrivals/i }).textContent ?? ""
    expect(summary).toContain("220 notices arrived")
    expect(summary).toContain("ADB procurement notices: 200 today")
    expect(summary).toContain("World Bank: 0 today")
  })

  it("says why it is empty rather than drawing an axis of zeroes", () => {
    const quiet = trends({
      intake: [
        { day: "2026-09-10", by_source: { adb: 0, wb: 0 } },
        { day: "2026-09-11", by_source: { adb: 0, wb: 0 } },
      ],
    })
    render(<PoolIntakeChart trends={quiet} />)
    expect(screen.getByText(/nothing has arrived/i)).toBeInTheDocument()
  })

  it("renders nothing at all before the data arrives", () => {
    const { container } = render(<PoolIntakeChart />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe("JobOutcomeChart", () => {
  it("reports the window's totals and today's failures", () => {
    render(<JobOutcomeChart trends={trends()} />)
    const summary = screen.getByRole("figure", { name: /outcomes/i }).textContent ?? ""
    expect(summary).toContain("48 succeeded")
    expect(summary).toContain("7 failed")
    expect(summary).toContain("Today: 5 failed of 35")
  })

  it("distinguishes a schedule that has stopped from one with nothing to do", () => {
    const silent = trends({
      jobs: [
        { day: "2026-09-10", succeeded: 0, failed: 0, partial: 0 },
        { day: "2026-09-11", succeeded: 0, failed: 0, partial: 0 },
      ],
    })
    render(<JobOutcomeChart trends={silent} />)
    expect(screen.getByText(/no job has run/i)).toBeInTheDocument()
  })
})

describe("SpendChart", () => {
  const usage = {
    daily_token_budget: 2_000_000,
    spent_today: 1_500,
    rows: [
      {
        day: "2026-09-10",
        purpose: "match_explanation",
        model: "gemini",
        calls: 4,
        tokens_in: 400,
        tokens_out: 100,
      },
      {
        day: "2026-09-11",
        purpose: "match_explanation",
        model: "gemini",
        calls: 6,
        tokens_in: 800,
        tokens_out: 200,
      },
      {
        day: "2026-09-11",
        purpose: "assistant_reply",
        model: "gemini",
        calls: 2,
        tokens_in: 400,
        tokens_out: 100,
      },
    ],
  }

  it("totals the tokens and names what spent them", () => {
    render(<SpendChart usage={usage} />)
    const summary =
      screen.getByRole("figure", { name: /where the tokens went/i }).textContent ?? ""
    expect(summary).toContain("2,000 tokens")
    expect(summary).toContain("Assistant reply")
    expect(summary).toContain("Match explanation")
  })

  it("says nothing has spent anything rather than drawing an empty plot", () => {
    render(<SpendChart usage={{ ...usage, rows: [] }} />)
    expect(screen.getByText(/no model calls recorded/i)).toBeInTheDocument()
  })
})
