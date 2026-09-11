import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"

import { server } from "@/mocks/server"
import { session, syncState } from "@/mocks/fixtures"
import { renderRoute, screen } from "@/test/render"

const NOTHING = { items: [], total: 0, page: 1, page_size: 10, pages: 0 }

function poolReturns(body: typeof NOTHING) {
  server.use(http.get("*/api/v1/tenders", () => HttpResponse.json(body)))
}

describe("the tender pool with nothing in it", () => {
  it("offers the pull when no filter is hiding anything", async () => {
    // The screen a new organization lands on before any portal has been read.
    // "Try a broader search term" is advice about a search nobody ran.
    poolReturns(NOTHING)
    server.use(
      http.get("*/api/v1/sources/sync", () =>
        HttpResponse.json({
          ...syncState,
          portals: syncState.portals.map((portal) => ({
            ...portal,
            last_run_at: null,
            last_success_at: null,
            last_status: null,
            last_notices_added: null,
          })),
        })
      )
    )

    await renderRoute("/app/tenders", { session: session() })

    expect(await screen.findByText("Nothing pulled yet")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sync now" })).toBeEnabled()
  })

  it("says the portals came back empty once they have been read", async () => {
    poolReturns(NOTHING)

    await renderRoute("/app/tenders", { session: session() })

    expect(
      await screen.findByText("The portals have nothing right now")
    ).toBeInTheDocument()
  })

  it("still blames the filter when one is applied", async () => {
    // A filter that excluded everything is the reader's own doing, and pulling
    // the portals would not change it.
    poolReturns(NOTHING)

    await renderRoute("/app/tenders?q=bridge", { session: session() })

    expect(
      await screen.findByText("No notices match these filters")
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Sync now" })
    ).not.toBeInTheDocument()
  })
})
