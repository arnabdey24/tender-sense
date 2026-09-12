import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { errorEnvelope } from "@/mocks/fixtures"
import { server } from "@/mocks/server"
import { renderRoute, screen, waitFor } from "@/test/render"

async function fillAndSubmit(email = "ada@example.com", password = "secret123") {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText("Email"), email)
  await user.type(await screen.findByLabelText("Password"), password)
  await user.click(screen.getByRole("button", { name: "Sign in" }))
  return user
}

describe("/login", () => {
  it("renders the Google link and the register link", async () => {
    await renderRoute("/login")

    // A plain anchor: the browser must follow the OAuth redirect itself.
    const google = await screen.findByText(/sign in with google/i)
    const anchor = google.closest("a")
    expect(anchor).toHaveAttribute(
      "href",
      "/api/v1/auth/google/start?redirect=%2Fapp%2Fdashboard"
    )
    expect(
      screen.getByRole("link", { name: /create an account/i })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: /forgot your password/i })
    ).toBeInTheDocument()
  })

  it("shows a field error taken from a 422 details array", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          errorEnvelope("validation_error", "Some fields need attention.", [
            { field: "password", message: "Password must be at least 10 characters" },
          ]),
          { status: 422 }
        )
      )
    )

    await renderRoute("/login")
    await fillAndSubmit()

    expect(
      await screen.findByText("Password must be at least 10 characters")
    ).toBeInTheDocument()
    // A field-level error is shown inline, not as a banner.
    expect(screen.queryByTestId("api-error")).not.toBeInTheDocument()
  })

  it("offers to resend the verification email on email_not_verified", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          errorEnvelope(
            "email_not_verified",
            "Verify your email address before signing in."
          ),
          { status: 403 }
        )
      )
    )

    await renderRoute("/login")
    const user = await fillAndSubmit()

    const alert = await screen.findByTestId("api-error")
    expect(alert).toHaveTextContent("Verify your email first")
    expect(alert).toHaveTextContent(
      "Verify your email address before signing in."
    )

    const resend = screen.getByRole("button", {
      name: /resend verification email/i,
    })
    await user.click(resend)

    await waitFor(() =>
      expect(screen.getByText("Verification email sent")).toBeInTheDocument()
    )
  })

  it("shows the rate_limited message plainly", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          errorEnvelope("rate_limited", "Too many attempts. Try again in 60s."),
          { status: 429 }
        )
      )
    )

    await renderRoute("/login")
    await fillAndSubmit()

    const alert = await screen.findByTestId("api-error")
    expect(alert).toHaveTextContent("Too many attempts. Try again in 60s.")
    expect(
      screen.queryByRole("button", { name: /resend verification email/i })
    ).not.toBeInTheDocument()
  })
})
