import userEvent from "@testing-library/user-event"
import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"

import { matches, session } from "@/mocks/fixtures"
import { server } from "@/mocks/server"
import { renderRoute, screen, waitFor, within } from "@/test/render"

function rowFor(title: string) {
  const link = screen.getByText(title)
  const row = link.closest("li")
  expect(row).not.toBeNull()
  return within(row!)
}

/**
 * Pressing Bid wrote a decision that nothing on the row rendered, so the only
 * feedback was a toast that vanished — scroll past the same notice a minute
 * later and there was nothing to say it had been dealt with.
 */
describe("a decision taken on the match feed", () => {
  it("shows on the row that already has one", async () => {
    await renderRoute("/app/matches", { session: session() })

    await screen.findByText("Rural electrification phase two")

    // The matcher says hold; the team said skip. The row shows the team's.
    expect(
      rowFor("Rural electrification phase two").getByRole("button", {
        name: "Skip",
      })
    ).toHaveAttribute("aria-pressed", "true")
    expect(
      rowFor("Rural electrification phase two").getByRole("button", {
        name: "Bid",
      })
    ).toHaveAttribute("aria-pressed", "false")

    // An untouched row makes no claim either way.
    expect(
      rowFor("Upgrade of the Dhaka bypass").getByRole("button", { name: "Bid" })
    ).toHaveAttribute("aria-pressed", "false")
  })

  it("records a bid and re-reads the feed so the row can change", async () => {
    // The server remembers, so the refetch the mutation triggers returns a
    // feed that has actually moved — which is the behaviour under test.
    const recorded: string[] = []
    server.use(
      http.put("*/api/v1/tenders/:tenderId/decision", async ({ request }) => {
        const body = (await request.json()) as { decision: string }
        recorded.push(body.decision)
        return HttpResponse.json({
          id: "9999aaaa-9999-4999-8999-999999999999",
          tender_id: matches[0].tender_id,
          decision: body.decision,
          note: null,
          is_current: true,
          decided_by_id: null,
          created_at: "2026-09-12T00:00:00Z",
        })
      }),
      http.get("*/api/v1/matches", () =>
        HttpResponse.json({
          items: [
            { ...matches[0], decision: recorded.at(-1) ?? null },
            matches[1],
          ],
          page: 1,
          page_size: 20,
          total: 2,
        })
      )
    )

    const user = userEvent.setup()
    await renderRoute("/app/matches", { session: session() })
    await screen.findByText("Upgrade of the Dhaka bypass")

    await user.click(
      rowFor("Upgrade of the Dhaka bypass").getByRole("button", { name: "Bid" })
    )

    await waitFor(() => expect(recorded).toEqual(["bid"]))
    await waitFor(() =>
      expect(
        rowFor("Upgrade of the Dhaka bypass").getByRole("button", {
          name: "Bid",
        })
      ).toHaveAttribute("aria-pressed", "true")
    )
  })

  it("withdraws when the decision already on the row is pressed again", async () => {
    let withdrawn = 0
    server.use(
      http.delete("*/api/v1/tenders/:tenderId/decision", () => {
        withdrawn += 1
        return new HttpResponse(null, { status: 204 })
      })
    )

    const user = userEvent.setup()
    await renderRoute("/app/matches", { session: session() })
    await screen.findByText("Rural electrification phase two")

    await user.click(
      rowFor("Rural electrification phase two").getByRole("button", {
        name: "Skip",
      })
    )

    await waitFor(() => expect(withdrawn).toBe(1))
  })
})
