import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"

import { server } from "@/mocks/server"
import { session } from "@/mocks/fixtures"
import { renderRoute, screen } from "@/test/render"

function staffSession() {
  const payload = session()
  return { ...payload, user: { ...payload.user, is_superuser: true } }
}

function memberSession() {
  const payload = session()
  return { ...payload, user: { ...payload.user, is_superuser: false } }
}

const OVERVIEW = {
  tenders: 146,
  tenders_open: 59,
  tenders_added_today: 3,
  organizations: 2,
  organizations_active: 2,
  users: 4,
  users_active: 4,
  sources: [
    {
      code: "egp_bd",
      name: "e-GP Bangladesh",
      health: "ok",
      enabled: true,
      last_success_at: "2026-09-11T08:00:00Z",
      tenders: 33,
    },
    {
      code: "manual",
      name: "Manually added",
      health: "ok",
      enabled: false,
      last_success_at: null,
      tenders: 0,
    },
  ],
  jobs_failed_24h: 0,
  scrapes_failed_24h: 0,
  email_queued: 0,
  email_failed: 0,
  ai_tokens_today: 0,
  ai_daily_token_budget: 2_000_000,
}

describe("the operations console", () => {
  it("turns a member away", async () => {
    // The API refuses them too; this only spares them a screen of 403s.
    await renderRoute("/admin", { session: memberSession() })

    expect(
      screen.queryByRole("heading", { name: "Operations" })
    ).not.toBeInTheDocument()
  })

  it("leads with the verdict, not the totals", async () => {
    server.use(
      http.get("*/api/v1/admin/overview", () => HttpResponse.json(OVERVIEW))
    )

    await renderRoute("/admin", { session: staffSession() })

    expect(
      await screen.findByText("Nothing is failing right now")
    ).toBeInTheDocument()
  })

  it("says what is wrong when something is", async () => {
    server.use(
      http.get("*/api/v1/admin/overview", () =>
        HttpResponse.json({
          ...OVERVIEW,
          jobs_failed_24h: 3,
          sources: [
            { ...OVERVIEW.sources[0], health: "down" },
            OVERVIEW.sources[1],
          ],
        })
      )
    )

    await renderRoute("/admin", { session: staffSession() })

    expect(await screen.findByText("Wants attention")).toBeInTheDocument()
    expect(
      screen.getByText(/1 portal not answering · 3 failed job runs/)
    ).toBeInTheDocument()
  })

  it("does not count a source that is never scraped as a broken portal", async () => {
    // `manual` holds hand-entered notices. Reporting it as "ok, never" put a
    // permanent non-event beside the portals that actually answer.
    server.use(
      http.get("*/api/v1/admin/overview", () => HttpResponse.json(OVERVIEW))
    )

    await renderRoute("/admin", { session: staffSession() })

    expect(await screen.findByText("not scraped")).toBeInTheDocument()
    expect(
      screen.queryByText(/portal not answering/)
    ).not.toBeInTheDocument()
  })
})
