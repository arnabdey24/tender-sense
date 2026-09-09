import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { errorEnvelope, invitationPreview, session } from "@/mocks/fixtures"
import { server } from "@/mocks/server"
import { renderRoute, screen } from "@/test/render"

describe("/invite/accept", () => {
  it("offers sign-in and sign-up while signed out", async () => {
    await renderRoute("/invite/accept?token=abc")

    const panel = await screen.findByTestId("invite-signed-out")
    expect(panel).toHaveTextContent("Acme Engineering")
    expect(panel).toHaveTextContent("Ada Lovelace invited")
    expect(panel).toHaveTextContent("alan@example.com")
    expect(screen.getByRole("tab", { name: "Sign in" })).toBeInTheDocument()
    expect(
      screen.getByRole("tab", { name: "Create account" })
    ).toBeInTheDocument()
  })

  it("warns when the signed-in address does not match the invitation", async () => {
    await renderRoute("/invite/accept?token=abc", { session: session() })

    const panel = await screen.findByTestId("invite-mismatch")
    // The invitation is for alan@, the session is ada@.
    expect(panel).toHaveTextContent(
      "This invitation is for a different address"
    )
    expect(panel).toHaveTextContent("alan@example.com")
    expect(panel).toHaveTextContent("ada@example.com")
    expect(
      screen.getByRole("button", { name: /sign in as a different user/i })
    ).toBeInTheDocument()
    expect(screen.queryByTestId("invite-accept")).not.toBeInTheDocument()
  })

  it("shows the accept button when the address matches", async () => {
    server.use(
      http.get("*/api/v1/invitations/:token", () =>
        HttpResponse.json({ ...invitationPreview, email: "ada@example.com" })
      )
    )

    await renderRoute("/invite/accept?token=abc", { session: session() })

    const panel = await screen.findByTestId("invite-accept")
    expect(panel).toHaveTextContent("Join Acme Engineering")
  })

  it("surfaces an expired invitation token", async () => {
    server.use(
      http.get("*/api/v1/invitations/:token", () =>
        HttpResponse.json(
          errorEnvelope("token_expired", "This invitation has expired."),
          { status: 400 }
        )
      )
    )

    await renderRoute("/invite/accept?token=abc")

    expect(await screen.findByTestId("api-error")).toHaveTextContent(
      "This invitation has expired."
    )
  })
})
