import userEvent from "@testing-library/user-event"
import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"

import { errorEnvelope, session } from "@/mocks/fixtures"
import { server } from "@/mocks/server"
import { renderRoute, screen, waitFor } from "@/test/render"

/**
 * The property under test throughout is that this produces a *draft*.
 * Nothing here may save, and nothing may overwrite what the person already
 * typed — they looked at the same website and reached their own conclusion,
 * and a button that discards that is a button nobody presses twice.
 */
describe("auto setup from a website", () => {
  it("fills the empty fields and says which page it read", async () => {
    const user = userEvent.setup()
    await renderRoute("/onboarding", { session: session({ memberships: [] }) })

    const website = await screen.findByLabelText("Website")
    await user.type(website, "https://padma-infra.com.bd")
    await user.click(
      screen.getByRole("button", { name: /auto setup from website/i })
    )

    await waitFor(() =>
      expect(screen.getByLabelText("Organization name")).toHaveValue(
        "Padma Infrastructure Ltd"
      )
    )
    expect(
      (screen.getByLabelText("What do you do?") as HTMLTextAreaElement).value
    ).toContain("rural roads")
    // Which of a company's domains it read is part of judging the answer.
    expect(await screen.findByText(/Drafted from/)).toBeInTheDocument()
  })

  it("leaves a field the person already filled in alone", async () => {
    const user = userEvent.setup()
    await renderRoute("/onboarding", { session: session({ memberships: [] }) })

    const name = await screen.findByLabelText("Organization name")
    await user.type(name, "The Name I Actually Use")
    await user.type(screen.getByLabelText("Website"), "https://padma-infra.com.bd")
    await user.click(
      screen.getByRole("button", { name: /auto setup from website/i })
    )

    await screen.findByText(/Drafted from/)
    expect(name).toHaveValue("The Name I Actually Use")
  })

  it("reports a site it could not read beside the address, and fills nothing", async () => {
    const user = userEvent.setup()
    await renderRoute("/onboarding", { session: session({ memberships: [] }) })

    await user.type(screen.getByLabelText("Website"), "https://nope.invalid")
    await user.click(
      screen.getByRole("button", { name: /auto setup from website/i })
    )

    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.getByLabelText("Organization name")).toHaveValue("")
  })

  it("cannot be pressed before an address is typed", async () => {
    await renderRoute("/onboarding", { session: session({ memberships: [] }) })

    expect(
      await screen.findByRole("button", { name: /auto setup from website/i })
    ).toBeDisabled()
  })

  it("saves nothing on its own", async () => {
    let created = 0
    server.use(
      http.post("*/api/v1/orgs", () => {
        created += 1
        return HttpResponse.json(errorEnvelope("x", "y"), { status: 500 })
      })
    )
    const user = userEvent.setup()
    await renderRoute("/onboarding", { session: session({ memberships: [] }) })

    await user.type(screen.getByLabelText("Website"), "https://padma-infra.com.bd")
    await user.click(
      screen.getByRole("button", { name: /auto setup from website/i })
    )
    await screen.findByText(/Drafted from/)

    expect(created).toBe(0)
  })
})

describe("improving a sentence", () => {
  it("stays disabled until there is something to improve", async () => {
    const user = userEvent.setup()
    await renderRoute("/onboarding", { session: session({ memberships: [] }) })

    const improve = await screen.findByRole("button", { name: /improve with ai/i })
    expect(improve).toBeDisabled()

    await user.type(
      screen.getByLabelText("What do you do?"),
      "we build rural roads"
    )

    await waitFor(() => expect(improve).toBeEnabled())
  })

  it("replaces the text and offers a way back", async () => {
    const user = userEvent.setup()
    await renderRoute("/onboarding", { session: session({ memberships: [] }) })

    const field = await screen.findByLabelText("What do you do?")
    await user.type(field, "we build rural roads")
    await user.click(screen.getByRole("button", { name: /improve with ai/i }))

    await waitFor(() =>
      expect(field).toHaveValue("we build rural roads (tightened)")
    )

    // Undo is what makes trying it free.
    await user.click(await screen.findByRole("button", { name: /undo/i }))
    expect(field).toHaveValue("we build rural roads")
  })
})
