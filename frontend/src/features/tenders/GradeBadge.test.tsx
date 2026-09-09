import { describe, expect, it } from "vitest"

import { GradeBadge } from "@/features/tenders/GradeBadge"
import { renderWithProviders, screen } from "@/test/render"

describe("GradeBadge", () => {
  it.each(["S", "A", "B", "C"] as const)("renders grade %s", (grade) => {
    renderWithProviders(<GradeBadge grade={grade} />)
    const badge = screen.getByText(grade)
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveAttribute("data-grade", grade)
    expect(badge).toHaveAttribute("aria-label", `Grade ${grade}`)
  })

  it("maps grade to the matching badge variant class", () => {
    renderWithProviders(<GradeBadge grade="S" />)
    expect(screen.getByText("S").className).toContain("bg-grade-s")
  })
})
