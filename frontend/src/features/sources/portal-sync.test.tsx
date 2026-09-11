import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { completeness, session } from "@/mocks/fixtures"
import { server } from "@/mocks/server"
import { renderRoute, screen } from "@/test/render"

/** Completeness as the API reports it, at whatever score a test needs. */
function scoring(score: number) {
  return http.get("*/api/v1/profile/completeness", () =>
    HttpResponse.json({ ...completeness, score })
  )
}

describe("sync with a thin capability profile", () => {
  it("says why a sync will not grade anything, and still allows it", async () => {
    server.use(scoring(20))

    await renderRoute("/app/settings/sources", { session: session() })

    expect(
      await screen.findByText(/none will be graded for your organization/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/20% complete/)).toBeInTheDocument()
    // The pool is shared, so the pull is still worth making for everyone else.
    expect(screen.getByRole("button", { name: "Sync now" })).toBeEnabled()
  })

  it("points at the page that fixes it", async () => {
    server.use(scoring(20))

    await renderRoute("/app/settings/sources", { session: session() })

    expect(
      await screen.findByRole("link", { name: /finish the profile/i })
    ).toHaveAttribute("href", "/app/settings/profile")
  })

  it("says nothing once the profile is worth matching against", async () => {
    server.use(scoring(85))

    await renderRoute("/app/settings/sources", { session: session() })

    expect(
      await screen.findByRole("button", { name: "Sync now" })
    ).toBeEnabled()
    expect(
      screen.queryByText(/none will be graded for your organization/i)
    ).not.toBeInTheDocument()
  })

  it("stays quiet at exactly the threshold", async () => {
    server.use(scoring(50))

    await renderRoute("/app/settings/sources", { session: session() })

    expect(
      await screen.findByRole("button", { name: "Sync now" })
    ).toBeEnabled()
    expect(
      screen.queryByText(/none will be graded for your organization/i)
    ).not.toBeInTheDocument()
  })
})
