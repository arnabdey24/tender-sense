import { http, HttpResponse } from "msw"
import { describe, expect, it, vi } from "vitest"

import { profile, session } from "@/mocks/fixtures"
import { server } from "@/mocks/server"
import { renderRoute, screen, waitFor, within } from "@/test/render"
import userEvent from "@testing-library/user-event"

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

/** One project already on the profile, for the list and edit paths. */
const storedProject = {
  id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  title: "District hospital network",
  client: "DGHS",
  sector: "healthcare",
  country: "BD",
  value: 45000000,
  currency: "BDT",
  started_on: "2024-01-01",
  completed_on: "2025-03-31",
}

describe("capability profile", () => {
  it("offers somewhere to put the past projects it scores", async () => {
    await renderRoute("/app/settings/profile", { session: session() })

    // The completeness strip grades past projects, so the page has to take them.
    expect(
      await screen.findByRole("heading", { name: "Past projects" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /add project/i })
    ).toBeInTheDocument()
  })

  it("sends a project the way the API stores one", async () => {
    const user = userEvent.setup()
    const posted = vi.fn()
    server.use(
      http.post("*/api/v1/profile/projects", async ({ request }) => {
        const body = await request.json()
        posted(body)
        return HttpResponse.json(
          { id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", ...(body as object) },
          { status: 201 }
        )
      })
    )

    await renderRoute("/app/settings/profile", { session: session() })
    await user.click(
      await screen.findByRole("button", { name: /add project/i })
    )

    const dialog = await screen.findByRole("dialog")
    await user.type(
      within(dialog).getByLabelText("Title"),
      "Core network upgrade"
    )
    await user.type(within(dialog).getByLabelText("Client"), "DGHS")
    await user.type(within(dialog).getByLabelText("Contract value"), "45000000")
    await user.click(
      within(dialog).getByRole("button", { name: /^add project$/i })
    )

    await waitFor(() =>
      expect(posted).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Core network upgrade",
          client: "DGHS",
          value: 45000000,
          // The turnover currency is the one the firm already quotes in.
          currency: "BDT",
        })
      )
    )
  })

  it("keeps an empty optional field out of the payload as null, not as ''", async () => {
    const user = userEvent.setup()
    const posted = vi.fn()
    server.use(
      http.post("*/api/v1/profile/projects", async ({ request }) => {
        const body = await request.json()
        posted(body)
        return HttpResponse.json(
          { id: "x", ...(body as object) },
          { status: 201 }
        )
      })
    )

    await renderRoute("/app/settings/profile", { session: session() })
    await user.click(
      await screen.findByRole("button", { name: /add project/i })
    )

    const dialog = await screen.findByRole("dialog")
    await user.type(
      within(dialog).getByLabelText("Title"),
      "Rural fibre rollout"
    )
    await user.click(
      within(dialog).getByRole("button", { name: /^add project$/i })
    )

    await waitFor(() =>
      expect(posted).toHaveBeenCalledWith(
        expect.objectContaining({
          client: null,
          description: null,
          sector: null,
          country: null,
          value: null,
          started_on: null,
          completed_on: null,
        })
      )
    )
  })

  it("refuses a completion date that precedes the start", async () => {
    const user = userEvent.setup()
    await renderRoute("/app/settings/profile", { session: session() })
    await user.click(
      await screen.findByRole("button", { name: /add project/i })
    )

    const dialog = await screen.findByRole("dialog")
    await user.type(
      within(dialog).getByLabelText("Title"),
      "Backwards project"
    )
    await user.type(within(dialog).getByLabelText("Started"), "2025-06-01")
    await user.type(within(dialog).getByLabelText("Completed"), "2024-01-01")
    await user.click(
      within(dialog).getByRole("button", { name: /^add project$/i })
    )

    expect(
      await within(dialog).findByText(/completion cannot precede the start/i)
    ).toBeInTheDocument()
  })

  it("lists what is already recorded and offers to remove it", async () => {
    server.use(
      http.get("*/api/v1/profile", () =>
        HttpResponse.json({ ...profile, past_projects: [storedProject] })
      )
    )

    await renderRoute("/app/settings/profile", { session: session() })

    expect(
      await screen.findByText("District hospital network")
    ).toBeInTheDocument()
    expect(
      screen.getByText(/DGHS · Healthcare · Bangladesh/)
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Remove District hospital network" })
    ).toBeInTheDocument()
  })

  it("edits a stored project in place rather than making a second one", async () => {
    const user = userEvent.setup()
    const put = vi.fn()
    server.use(
      http.get("*/api/v1/profile", () =>
        HttpResponse.json({ ...profile, past_projects: [storedProject] })
      ),
      http.put("*/api/v1/profile/projects/:id", async ({ request, params }) => {
        const body = await request.json()
        put({ id: params.id, body })
        return HttpResponse.json({ id: params.id, ...(body as object) })
      })
    )

    await renderRoute("/app/settings/profile", { session: session() })
    await user.click(
      await screen.findByRole("button", {
        name: "Edit District hospital network",
      })
    )

    // The form opens on what is stored, not on a blank slate.
    const dialog = await screen.findByRole("dialog")
    const title = within(dialog).getByLabelText("Title")
    expect(title).toHaveValue("District hospital network")
    expect(within(dialog).getByLabelText("Client")).toHaveValue("DGHS")

    await user.clear(title)
    await user.type(title, "District hospital core network")
    await user.click(
      within(dialog).getByRole("button", { name: /^save project$/i })
    )

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith({
        id: storedProject.id,
        body: expect.objectContaining({
          title: "District hospital core network",
          // Untouched fields survive the round trip; PUT replaces the whole row.
          client: "DGHS",
          sector: "healthcare",
          country: "BD",
          value: 45000000,
        }),
      })
    )
  })

  it("hides the whole section from a plain member", async () => {
    await renderRoute("/app/settings/profile", { session: memberSession() })

    expect(
      await screen.findByRole("heading", { name: "Capabilities" })
    ).toBeInTheDocument()
    // The completeness badge still names it; only the editor is admin-only.
    expect(
      screen.queryByRole("heading", { name: "Past projects" })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /add project/i })
    ).not.toBeInTheDocument()
  })
})
