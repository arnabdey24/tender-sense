import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { errorEnvelope, session } from "@/mocks/fixtures"
import { server } from "@/mocks/server"
import { renderRoute, screen, waitFor } from "@/test/render"

describe("/verify-email", () => {
  it("shows the expired-link state and can request a new email", async () => {
    server.use(
      http.post("*/api/v1/auth/verify-email", () =>
        HttpResponse.json(
          errorEnvelope(
            "token_expired",
            "This verification link has expired. Request a new one."
          ),
          { status: 400 }
        )
      )
    )

    await renderRoute("/verify-email?token=stale-token")

    const expired = await screen.findByTestId("verify-expired")
    expect(expired).toHaveTextContent("That link has expired")
    expect(expired).toHaveTextContent(
      "This verification link has expired. Request a new one."
    )

    const user = userEvent.setup()
    const email = screen.getByLabelText(/send a new verification link/i)
    await user.type(email, "ada@example.com")
    await user.click(screen.getByRole("button", { name: /send new link/i }))

    await waitFor(() =>
      expect(screen.getByText("Verification email sent")).toBeInTheDocument()
    )
  })

  it("treats a link with no token as invalid", async () => {
    await renderRoute("/verify-email")

    const expired = await screen.findByTestId("verify-expired")
    expect(expired).toHaveTextContent("missing its verification token")
  })

  it("signs the user in and routes to the dashboard", async () => {
    const { router } = await renderRoute("/verify-email?token=good-token")

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/app/dashboard")
    )
  })

  it("routes to onboarding when the verified user has no organization", async () => {
    server.use(
      http.post("*/api/v1/auth/verify-email", () =>
        HttpResponse.json(session({ memberships: [], active_org_id: null }))
      )
    )

    const { router } = await renderRoute("/verify-email?token=good-token")

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/onboarding")
    )
  })
})
