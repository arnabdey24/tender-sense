import type { components } from "@/lib/api/schema"

type SessionResponse = components["schemas"]["SessionResponse"]
type UserRead = components["schemas"]["UserRead"]
type MemberRead = components["schemas"]["MemberRead"]
type InvitationRead = components["schemas"]["InvitationRead"]
type InvitationPreview = components["schemas"]["InvitationPreview"]
type OrganizationRead = components["schemas"]["OrganizationRead"]
type NotificationRead = components["schemas"]["NotificationRead"]
type NotificationSettingsRead =
  components["schemas"]["NotificationSettingsRead"]
type RecipientRead = components["schemas"]["RecipientRead"]

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

/** In-app notifications for the centre. */
export const notifications: NotificationRead[] = [
  {
    id: "55555555-5555-4555-8555-555555555555",
    type: "instant_match",
    title: "Grade S match: Enterprise network switches",
    body: "Strong overlap with your networking work.",
    link: "/app/tenders/66666666-6666-4666-8666-666666666666",
    tender_id: "66666666-6666-4666-8666-666666666666",
    data: {},
    created_at: new Date().toISOString(),
    read: false,
  },
  {
    id: "77777777-7777-4777-8777-777777777777",
    type: "deadline_reminder",
    title: "2 days left: Road resurfacing",
    body: "You marked this one as a bid.",
    link: "/app/tenders/88888888-8888-4888-8888-888888888888",
    tender_id: "88888888-8888-4888-8888-888888888888",
    data: { days_left: 2 },
    created_at: new Date().toISOString(),
    read: true,
  },
]

export const notificationSettings: NotificationSettingsRead = {
  inapp_enabled: true,
  instant_enabled: true,
  instant_min_grade: "S",
  instant_requires_eligible: true,
  digest_enabled: true,
  digest_time: "08:00:00",
  digest_timezone: "Asia/Dhaka",
  digest_min_grade: "B",
  reminders_enabled: true,
  reminder_offsets: [7, 2],
}

export const recipients: RecipientRead[] = [
  {
    id: "99999999-9999-4999-8999-999999999999",
    email: "bids@example.com",
    name: "Bid desk",
    types: [],
    verified_at: new Date().toISOString(),
    unsubscribed_at: null,
    created_at: new Date().toISOString(),
  },
]
