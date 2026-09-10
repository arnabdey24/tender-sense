import { describe, expect, it } from "vitest"

import { SourceHealthBadge } from "@/features/sources/SourceHealthBadge"
import { renderWithProviders, screen } from "@/test/render"

describe("SourceHealthBadge", () => {
  it("names each state in words a reader can act on", () => {
    renderWithProviders(<SourceHealthBadge health="ok" />)
    expect(screen.getByText("Healthy")).toBeInTheDocument()
  })

  it("keeps degraded visually distinct from down", () => {
    // One timeout is weather; three failures in a row is a broken portal.
    // Collapsing the two would either cry wolf or hide a real outage.
    const degraded = renderWithProviders(
      <SourceHealthBadge health="degraded" />
    )
    const degradedClass = screen.getByText("Degraded").className
    degraded.unmount()

    renderWithProviders(<SourceHealthBadge health="down" />)
    expect(screen.getByText("Down").className).not.toBe(degradedClass)
  })
})
