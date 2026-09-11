import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"
import userEvent from "@testing-library/user-event"

import { server } from "@/mocks/server"
import { session, syncState } from "@/mocks/fixtures"
import { renderRoute, screen } from "@/test/render"

/** The signed-in user is a plain member — no platform staff rights at all. */
function memberSession() {
  const payload = session()
  return {
    ...payload,
    user: { ...payload.user, is_superuser: false },
  }
}

describe("pulling the portals by hand", () => {
  it("offers the pull to an ordinary member", async () => {
    // The whole point of moving it off the operator page: the person looking at
    // an empty pool is rarely the person with staff rights.
    await renderRoute("/app/settings/sources", { session: memberSession() })

    expect(
      await screen.findByRole("button", { name: "Sync now" })
    ).toBeEnabled()
  })

  it("reports what the last pass over each portal found", async () => {
    await renderRoute("/app/settings/sources", { session: memberSession() })

    expect(await screen.findByText(/3 new/)).toBeInTheDocument()
    expect(screen.getByText(/nothing new/)).toBeInTheDocument()
  })

  it("shows the wait rather than an error when the cooldown is running", async () => {
    // A refusal inside the window is a legitimate answer, not a failure, and
    // must not reach the reader as one.
    server.use(
      http.get("*/api/v1/sources/sync", () =>
        HttpResponse.json({ ...syncState, retry_after_seconds: 540 })
      )
    )

    await renderRoute("/app/settings/sources", { session: memberSession() })

    expect(
      await screen.findByRole("button", { name: /Again in 9 min/ })
    ).toBeDisabled()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("says a portal is working rather than showing a stale timestamp", async () => {
    server.use(
      http.get("*/api/v1/sources/sync", () =>
        HttpResponse.json({
          ...syncState,
          running: true,
          portals: syncState.portals.map((portal, index) => ({
            ...portal,
            running: index === 0,
          })),
        })
      )
    )

    await renderRoute("/app/settings/sources", { session: memberSession() })

    expect(
      await screen.findByText("Working through the portal now")
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Syncing…" })).toBeDisabled()
  })

  it("starts a pull when pressed", async () => {
    await renderRoute("/app/settings/sources", { session: memberSession() })

    await userEvent.click(
      await screen.findByRole("button", { name: "Sync now" })
    )

    expect(await screen.findByText(/Syncing 2 portals/)).toBeInTheDocument()
  })
})
