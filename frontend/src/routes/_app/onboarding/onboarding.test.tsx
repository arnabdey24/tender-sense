import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { organization, session } from "@/mocks/fixtures"
import { server } from "@/mocks/server"
import { renderRoute, screen, waitFor } from "@/test/render"

describe("/onboarding", () => {
  it("creates an org, refreshes for the org claim, then goes to the dashboard", async () => {
    const orgless = session({ memberships: [], active_org_id: null })
    let refreshes = 0
    let created = false

    server.use(
      http.post("*/api/v1/auth/refresh", () => {
        refreshes += 1
        // The first refresh boots the org-less session; once the org exists the
        // backend mints a token that finally carries the org claim.
        return HttpResponse.json(created ? session() : orgless)
      }),
      http.post("*/api/v1/orgs", () => {
        created = true
        return HttpResponse.json(organization, { status: 201 })
      })
    )

    // No `session` option here: this test owns the refresh handler so it can
    // change what the refresh returns once the organization exists.
    const { router } = await renderRoute("/onboarding")

    const user = userEvent.setup()
    await user.type(
      await screen.findByLabelText("Organization name"),
      "Acme Engineering"
    )
    await user.click(
      screen.getByRole("button", { name: /create organization/i })
    )

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/app/dashboard")
    )
    // Boot refresh + the post-create refresh that picks up the org claim.
    expect(refreshes).toBeGreaterThanOrEqual(2)
  })

  it("submits the country as an ISO alpha-2 code, not its display name", async () => {
    // Regression: the picker used to offer country names, which the API
    // rejects with "country must be a 2-letter ISO 3166-1 alpha-2 code", so
    // choosing a country made the organization impossible to create.
    const orgless = session({ memberships: [], active_org_id: null })
    let body: { country?: string } | null = null

    server.use(
      http.post("*/api/v1/auth/refresh", () => HttpResponse.json(orgless)),
      http.post("*/api/v1/orgs", async ({ request }) => {
        body = (await request.json()) as { country?: string }
        return HttpResponse.json(organization, { status: 201 })
      })
    )

    await renderRoute("/onboarding")

    const user = userEvent.setup()
    await user.type(
      await screen.findByLabelText("Organization name"),
      "Acme Engineering"
    )
    await user.type(screen.getByLabelText("Country"), "Bangla")
    await user.click(await screen.findByRole("option", { name: "Bangladesh" }))
    await user.click(
      screen.getByRole("button", { name: /create organization/i })
    )

    await waitFor(() => expect(body).not.toBeNull())
    expect(body!.country).toBe("BD")
  })

  it("sends a user who already has an organization to the dashboard", async () => {
    const { router } = await renderRoute("/onboarding", { session: session() })
    expect(router.state.location.pathname).toBe("/app/dashboard")
  })
})
