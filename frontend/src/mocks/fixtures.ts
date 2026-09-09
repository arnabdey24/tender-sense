import type { components } from "@/lib/api/schema"

type SessionResponse = components["schemas"]["SessionResponse"]
type UserRead = components["schemas"]["UserRead"]
type MemberRead = components["schemas"]["MemberRead"]
type InvitationRead = components["schemas"]["InvitationRead"]
type InvitationPreview = components["schemas"]["InvitationPreview"]
type OrganizationRead = components["schemas"]["OrganizationRead"]

export const ORG_ID = "11111111-1111-4111-8111-111111111111"
export const OTHER_ORG_ID = "22222222-2222-4222-8222-222222222222"
export const USER_ID = "33333333-3333-4333-8333-333333333333"
export const OTHER_USER_ID = "44444444-4444-4444-8444-444444444444"

export const user: UserRead = {
  id: USER_ID,
  email: "ada@example.com",
  full_name: "Ada Lovelace",
  avatar_url: null,
  email_verified: true,
  has_password: true,
  is_superuser: false,
  created_at: "2026-01-01T00:00:00Z",
}

/** A signed-in session with one organization where the user is an admin. */
export function session(
  overrides: Partial<SessionResponse> = {}
): SessionResponse {
  return {
    access_token: "test-access-token",
    token_type: "bearer",
    expires_at: "2099-01-01T00:00:00Z",
    user,
    memberships: [
      {
        org_id: ORG_ID,
        org_name: "Acme Engineering",
        org_slug: "acme-engineering",
        role: "admin",
      },
    ],
    active_org_id: ORG_ID,
    ...overrides,
  }
}

export const organization: OrganizationRead = {
  id: ORG_ID,
  name: "Acme Engineering",
  slug: "acme-engineering",
  country: "Bangladesh",
  website: "https://acme.example",
  description: null,
  timezone: "Asia/Dhaka",
  plan: "free",
  created_at: "2026-01-01T00:00:00Z",
}

export const members: MemberRead[] = [
  {
    user_id: USER_ID,
    email: "ada@example.com",
    full_name: "Ada Lovelace",
    avatar_url: null,
    role: "admin",
    status: "active",
    joined_at: "2026-01-01T00:00:00Z",
  },
  {
    user_id: OTHER_USER_ID,
    email: "grace@example.com",
    full_name: "Grace Hopper",
    avatar_url: null,
    role: "member",
    status: "active",
    joined_at: "2026-02-01T00:00:00Z",
  },
]

export const invitations: InvitationRead[] = [
  {
    id: "55555555-5555-4555-8555-555555555555",
    email: "alan@example.com",
    role: "member",
    expires_at: "2099-01-08T00:00:00Z",
    created_at: "2026-03-01T00:00:00Z",
    invited_by_name: "Ada Lovelace",
    status: "pending",
  },
]

export const invitationPreview: InvitationPreview = {
  org_name: "Acme Engineering",
  inviter_name: "Ada Lovelace",
  role: "member",
  email: "alan@example.com",
  expires_at: "2099-01-08T00:00:00Z",
  requires_signup: false,
}

/** The backend's error envelope, used by every failure handler. */
export function errorEnvelope(
  code: string,
  message: string,
  details?: { field: string; message: string }[]
) {
  return { error: { code, message, ...(details ? { details } : {}) } }
}
