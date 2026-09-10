import { describe, expect, it } from "vitest"

import { SourceHealthBadge } from "@/features/sources/SourceHealthBadge"
import { renderWithProviders, screen } from "@/test/render"

describe("SourceHealthBadge", () => {
  it("names each state in words a reader can act on", () => {
    renderWithProviders(<SourceHealthBadge health="ok" />)
    expect(screen.getByText("Healthy")).toBeInTheDocument()
  })

  it("reports a paused source as paused, not as its stale health", () => {
    // A source nobody is polling has no health to report; showing the "ok" from
    // before it was switched off is how a dead portal looks fine.
    renderWithProviders(<SourceHealthBadge health="ok" enabled={false} />)
    expect(screen.getByText("Paused")).toBeInTheDocument()
    expect(screen.queryByText("Healthy")).not.toBeInTheDocument()
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
