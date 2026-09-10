import { describe, expect, it } from "vitest"

import { session } from "@/mocks/fixtures"
import { renderRoute, screen } from "@/test/render"

/** The same session, but the signed-in user is a plain member. */
function memberSession() {
  const payload = session()
  return {
    ...payload,
    memberships: (payload.memberships ?? []).map((m) => ({
      ...m,
      role: "member" as const,
    })),
  }
}

describe("notification settings", () => {
  it("shows the delivery choices with the organization's own timings", async () => {
    await renderRoute("/app/settings/notifications", { session: session() })

    expect(await screen.findByLabelText("Instant alerts")).toBeChecked()
    expect(screen.getByLabelText("Digest send time")).toHaveValue("08:00")
  })

  it("says an address receives nothing until someone confirms it", async () => {
    await renderRoute("/app/settings/notifications", { session: session() })

    expect(
      await screen.findByText(
        /receives nothing until someone holding it confirms/i
      )
    ).toBeInTheDocument()
  })

  it("keeps every control read-only for a plain member", async () => {
    await renderRoute("/app/settings/notifications", {
      session: memberSession(),
    })

    // Base UI marks a disabled switch with `data-disabled`, not the attribute.
    expect(await screen.findByLabelText("Instant alerts")).toHaveAttribute(
      "data-disabled"
    )
    expect(
      screen.getByText("Ask an admin to change these.")
    ).toBeInTheDocument()
    // Adding a recipient mails an arbitrary address, so it is admin-only.
    expect(
      screen.queryByRole("button", { name: /add recipient/i })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /send myself a test message/i })
    ).not.toBeInTheDocument()
  })

  it("offers a way to prove delivery works before an alert depends on it", async () => {
    await renderRoute("/app/settings/notifications", { session: session() })

    expect(
      await screen.findByRole("button", { name: /send myself a test message/i })
    ).toBeInTheDocument()
  })
})
