import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"

import { decisions, session } from "@/mocks/fixtures"
import { server } from "@/mocks/server"
import { renderRoute, screen, within } from "@/test/render"

/**
 * The pipeline used to read `/pipeline`, which returns *matches* the model
 * recommends bidding on. Two bugs fell out of that one wiring mistake: the
 * page duplicated Matches whenever nothing graded C, and a decision recorded
 * against an unscored tender — which is every decision a company makes before
 * it finishes its profile — had no match row to be returned as, so it showed
 * up nowhere in the product at all.
 */
describe("/app/pipeline", () => {
  it("lists what was decided, including a bid on a tender with no grade", async () => {
    await renderRoute("/app/pipeline", { session: session() })

    expect(await screen.findByText("2 in play")).toBeInTheDocument()

    const scored = await screen.findByText("Upgrade of the Dhaka bypass")
    expect(scored).toBeInTheDocument()

    // The bid recorded before the profile existed. It has no grade to show,
    // and dropping it for that reason is the bug.
    const unscored = screen.getByText("Supply of laboratory equipment")
    const row = unscored.closest("li")
    expect(row).not.toBeNull()
    expect(within(row!).getByText(/Not scored/)).toBeInTheDocument()
    expect(
      within(row!).getByRole("link", { name: "finish your profile" })
    ).toBeInTheDocument()
  })

  it("reads decisions, not the recommendation feed", async () => {
    let pipelineCalls = 0
    server.use(
      http.get("*/api/v1/pipeline", () => {
        pipelineCalls += 1
        return HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 })
      })
    )

    await renderRoute("/app/pipeline", { session: session() })
    await screen.findByText("2 in play")

    expect(pipelineCalls).toBe(0)
  })

  it("shows the note, which is the reason the trail exists", async () => {
    await renderRoute("/app/pipeline", { session: session() })

    expect(
      await screen.findByText(/three of these for the same buyer/)
    ).toBeInTheDocument()
  })

  it("counts skips out of play rather than listing them", async () => {
    server.use(
      http.get("*/api/v1/decisions", () =>
        HttpResponse.json({
          items: [
            ...decisions,
            {
              ...decisions[0],
              id: "cccc1111-1111-4111-8111-cccccccccccc",
              decision: "skip",
              note: null,
              tender: { ...decisions[0].tender, title: "Not for us" },
            },
          ],
          page: 1,
          page_size: 20,
          total: 3,
        })
      )
    )

    await renderRoute("/app/pipeline", { session: session() })

    expect(await screen.findByText("2 in play")).toBeInTheDocument()
    expect(screen.getByText(/1 skipped, not shown/)).toBeInTheDocument()
    expect(screen.queryByText("Not for us")).not.toBeInTheDocument()
  })

  it("says so, and points at Matches, when nothing has been decided", async () => {
    server.use(
      http.get("*/api/v1/decisions", () =>
        HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 })
      )
    )

    await renderRoute("/app/pipeline", { session: session() })

    const empty = await screen.findByText("Nothing in the pipeline yet")
    expect(empty).toBeInTheDocument()

    // Scoped to the page: the sidebar carries a "Matches" link on every route.
    const pointer = screen.getByText(/The graded shortlist is on/)
    expect(
      within(pointer).getByRole("link", { name: "Matches" })
    ).toBeInTheDocument()
  })
})
