import { describe, expect, it } from "vitest"

import { session } from "@/mocks/fixtures"
import { renderRoute, screen } from "@/test/render"

describe("the notification centre", () => {
  it("shows what came in, labelled by kind", async () => {
    await renderRoute("/app/notifications", { session: session() })

    expect(
      await screen.findByText("Grade S match: Enterprise network switches")
    ).toBeInTheDocument()
    // A deadline must not read as a new match.
    expect(screen.getByText("Strong match")).toBeInTheDocument()
    expect(screen.getByText("Deadline")).toBeInTheDocument()
  })

  it("distinguishes unread from read at a glance", async () => {
    await renderRoute("/app/notifications", { session: session() })

    await screen.findByText("Grade S match: Enterprise network switches")
    // One of the two fixtures is read, so exactly one dot is expected.
    expect(screen.getAllByLabelText("Unread")).toHaveLength(1)
    expect(screen.getAllByRole("button", { name: "Mark read" })).toHaveLength(1)
  })

  it("puts the unread count on the bell so it is visible from any page", async () => {
    await renderRoute("/app/notifications", { session: session() })

    expect(
      await screen.findByLabelText("Notifications (1 unread)")
    ).toBeInTheDocument()
  })
})
