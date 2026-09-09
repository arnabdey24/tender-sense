import { describe, expect, it } from "vitest"

import { MembersTable } from "@/features/org/MembersTable"
import { members, USER_ID } from "@/mocks/fixtures"
import { renderWithProviders, screen } from "@/test/render"

describe("MembersTable", () => {
  it("hides every admin-only control from a plain member", () => {
    renderWithProviders(
      <MembersTable members={members} isAdmin={false} currentUserId={USER_ID} />
    )

    // Roles are read-only badges, not selects.
    expect(
      screen.queryByLabelText("Role for grace@example.com")
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /remove grace@example.com/i })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("columnheader", { name: "Actions" })
    ).not.toBeInTheDocument()

    // The data itself is still visible.
    expect(screen.getByText("Grace Hopper")).toBeInTheDocument()
    expect(screen.getByText("grace@example.com")).toBeInTheDocument()
  })

  it("gives admins a role select and a remove action for other members", () => {
    renderWithProviders(
      <MembersTable members={members} isAdmin currentUserId={USER_ID} />
    )

    expect(
      screen.getByLabelText("Role for grace@example.com")
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /remove grace@example.com/i })
    ).toBeEnabled()
    expect(
      screen.getByRole("columnheader", { name: "Actions" })
    ).toBeInTheDocument()
  })

  it("disables the admin's own role and remove controls", () => {
    renderWithProviders(
      <MembersTable members={members} isAdmin currentUserId={USER_ID} />
    )

    // The backend rejects self-changes with cannot_change_own_role / last_admin.
    expect(screen.getByLabelText("Role for ada@example.com")).toBeDisabled()
    expect(
      screen.getByRole("button", { name: /remove ada@example.com/i })
    ).toBeDisabled()
    expect(screen.getByText("You")).toBeInTheDocument()
  })

  it("renders an empty state when nobody is listed", () => {
    renderWithProviders(<MembersTable members={[]} isAdmin />)
    expect(screen.getByText("No members yet")).toBeInTheDocument()
  })
})
