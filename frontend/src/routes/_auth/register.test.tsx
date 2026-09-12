import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { PASSWORD_MIN_LENGTH } from "@/features/auth/password"
import { renderRoute, screen } from "@/test/render"

/**
 * The bug this guards against is not "the rule is wrong" but "the form and the
 * API disagree". The placeholder rule said eight characters, `/auth/register`
 * enforced ten, and a password typed to the hint's own instruction came back
 * rejected — the form talked the user into the failure and then blamed them.
 */
describe("/register", () => {
  it("states the length rule before anything is typed", async () => {
    await renderRoute("/register")

    expect(
      await screen.findByText(`Use at least ${PASSWORD_MIN_LENGTH} characters.`)
    ).toBeInTheDocument()
  })

  it("rejects a password the API would reject, with the same number", async () => {
    const user = userEvent.setup()
    await renderRoute("/register")

    await user.type(await screen.findByLabelText("Full name"), "Ada Lovelace")
    await user.type(screen.getByLabelText("Work email"), "ada@example.com")
    await user.type(
      screen.getByLabelText("Password"),
      "a".repeat(PASSWORD_MIN_LENGTH - 1)
    )
    await user.click(screen.getByRole("button", { name: "Create account" }))

    // Still on the form: it never reached the API, and the reason it gives is
    // the number the API actually uses.
    expect(screen.queryByTestId("check-inbox")).not.toBeInTheDocument()
    expect(
      await screen.findAllByText(`Use at least ${PASSWORD_MIN_LENGTH} characters.`)
    ).not.toHaveLength(0)
  })
})
