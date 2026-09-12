import userEvent from "@testing-library/user-event"
import { HttpResponse, http } from "msw"
import { afterEach, describe, expect, it, vi } from "vitest"

import { server } from "@/mocks/server"
import { session, syncState } from "@/mocks/fixtures"
import { resetAutoSync } from "@/features/sources/use-portal-sync"
import { renderRoute, screen, waitFor } from "@/test/render"

afterEach(() => resetAutoSync())

/** Counts the presses so a guard that fails is visible as a number. */
function watchSync(state: Partial<typeof syncState> = {}) {
  const presses = vi.fn()
  server.use(
    http.get("*/api/v1/sources/sync", () =>
      HttpResponse.json({ ...syncState, ...state })
    ),
    http.post("*/api/v1/sources/sync", () => {
      presses()
      return HttpResponse.json({
        ...syncState,
        ...state,
        running: true,
        queued: ["egp_bd", "wb"],
      })
    })
  )
  return presses
}

describe("the dashboard on a deployment with an empty pool", () => {
  it("starts a pull by itself", async () => {
    // The case this exists for: nobody has filled this deployment, and the new
    // organization has no reason to know that is what is wrong.
    const presses = watchSync({ pool_size: 0 })

    await renderRoute("/app/dashboard", { session: session() })

    await waitFor(() => expect(presses).toHaveBeenCalledTimes(1))
  })

  it("does not start one when the pool has notices in it", async () => {
    // A full pool and no matches is a profile or rules problem. Pulling the
    // portals again would change nothing, and would spend a cooldown that is
    // shared with every other organization on the deployment.
    const presses = watchSync({ pool_size: 146 })

    await renderRoute("/app/dashboard", { session: session() })
    await screen.findByRole("heading", { name: "Dashboard" })

    expect(presses).not.toHaveBeenCalled()
  })

  it("does not start one while a pull is already running", async () => {
    const presses = watchSync({ pool_size: 0, running: true })

    await renderRoute("/app/dashboard", { session: session() })
    await screen.findByRole("heading", { name: "Dashboard" })

    expect(presses).not.toHaveBeenCalled()
  })

  it("does not start one when the operator has switched it off", async () => {
    // The console's own setting. Acting without being asked is exactly the
    // behaviour an operator should be able to decline without a redeploy.
    const presses = watchSync({ pool_size: 0, auto_sync: false })

    await renderRoute("/app/dashboard", { session: session() })
    await screen.findByRole("heading", { name: "Dashboard" })

    expect(presses).not.toHaveBeenCalled()
  })

  it("does not start one inside the cooldown", async () => {
    // Ten people opening an empty dashboard at nine in the morning must produce
    // one pull between them, not ten.
    const presses = watchSync({ pool_size: 0, retry_after_seconds: 540 })

    await renderRoute("/app/dashboard", { session: session() })
    await screen.findByRole("heading", { name: "Dashboard" })

    expect(presses).not.toHaveBeenCalled()
  })

  it("tries only once per tab, however often the page is opened", async () => {
    const presses = watchSync({ pool_size: 0 })

    await renderRoute("/app/dashboard", { session: session() })
    await waitFor(() => expect(presses).toHaveBeenCalledTimes(1))

    await renderRoute("/app/dashboard", { session: session() })
    await screen.findAllByRole("heading", { name: "Dashboard" })

    expect(presses).toHaveBeenCalledTimes(1)
  })
})

describe("the sync control on the daily surfaces", () => {
  it("is on the dashboard", async () => {
    watchSync({ pool_size: 146 })

    await renderRoute("/app/dashboard", { session: session() })

    expect(
      await screen.findByRole("button", { name: "Sync now" })
    ).toBeEnabled()
  })

  it("is on Today, without outranking where the reader is going next", async () => {
    watchSync({ pool_size: 146 })

    await renderRoute("/app/today", { session: session() })

    const sync = await screen.findByRole("button", { name: "Sync now" })
    const onward = screen.getByText("All matches")
    // Document order: the navigation sits to the right of it, which in a
    // right-aligned group is the more prominent position.
    expect(
      sync.compareDocumentPosition(onward) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
  })
})

/**
 * A count beside two words is not a definition. "Needs checking: 3" reads
 * either as three broken records or as three rejections, and it is neither —
 * it is three notices that did not say enough for a rule to decide, waiting
 * on a person. Both misreadings stop somebody bidding.
 */
describe("what each dashboard queue actually contains", () => {
  it("says it, with rows on screen rather than only when empty", async () => {
    const user = userEvent.setup()
    watchSync({ pool_size: 146 })

    await renderRoute("/app/dashboard", { session: session() })

    expect(
      await screen.findByText(/Graded S or A since yesterday/)
    ).toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /Needs checking/ }))

    expect(
      await screen.findByText(/eligibility cannot be decided from it/)
    ).toBeInTheDocument()
    expect(screen.getByText(/Not a rejection/)).toBeInTheDocument()
  })
})
