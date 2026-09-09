import { beforeEach, describe, expect, it } from "vitest"

import { activeRole, useAuthStore } from "@/lib/auth/store"
import { ORG_ID, OTHER_ORG_ID, session } from "@/mocks/fixtures"

function reset() {
  useAuthStore.setState({
    status: "booting",
    accessToken: null,
    user: null,
    memberships: [],
    activeOrgId: null,
  })
}

describe("auth store", () => {
  beforeEach(reset)

  it("starts in the booting state with nothing loaded", () => {
    const state = useAuthStore.getState()
    expect(state.status).toBe("booting")
    expect(state.accessToken).toBeNull()
    expect(state.user).toBeNull()
    expect(state.memberships).toEqual([])
  })

  it("adopts a session payload", () => {
    useAuthStore.getState().setSession(session())
    const state = useAuthStore.getState()
    expect(state.status).toBe("authed")
    expect(state.accessToken).toBe("test-access-token")
    expect(state.user?.email).toBe("ada@example.com")
    expect(state.activeOrgId).toBe(ORG_ID)
    expect(activeRole(state)).toBe("admin")
  })

  it("treats a session without memberships as org-less", () => {
    useAuthStore
      .getState()
      .setSession(session({ memberships: [], active_org_id: null }))
    const state = useAuthStore.getState()
    expect(state.status).toBe("authed")
    expect(state.memberships).toEqual([])
    expect(activeRole(state)).toBeNull()
  })

  it("replaces the access token without dropping the session", () => {
    useAuthStore.getState().setSession(session())
    useAuthStore.getState().setAccessToken("token-with-org-claim")
    const state = useAuthStore.getState()
    expect(state.accessToken).toBe("token-with-org-claim")
    expect(state.status).toBe("authed")
    expect(state.user).not.toBeNull()
  })

  it("tracks the active organization when switching", () => {
    useAuthStore.getState().setSession(
      session({
        memberships: [
          {
            org_id: ORG_ID,
            org_name: "Acme",
            org_slug: "acme",
            role: "admin",
          },
          {
            org_id: OTHER_ORG_ID,
            org_name: "Globex",
            org_slug: "globex",
            role: "member",
          },
        ],
      })
    )
    useAuthStore.getState().setActiveOrg(OTHER_ORG_ID)
    expect(activeRole(useAuthStore.getState())).toBe("member")
  })

  it("clears everything on logout and on markAnon", () => {
    useAuthStore.getState().setSession(session())
    useAuthStore.getState().logout()
    let state = useAuthStore.getState()
    expect(state.status).toBe("anon")
    expect(state.accessToken).toBeNull()
    expect(state.memberships).toEqual([])

    useAuthStore.getState().setSession(session())
    useAuthStore.getState().markAnon()
    state = useAuthStore.getState()
    expect(state.status).toBe("anon")
    expect(state.user).toBeNull()
  })
})
