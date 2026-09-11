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
type ProfileRead = components["schemas"]["ProfileRead"]
type CompletenessRead = components["schemas"]["CompletenessRead"]
type TaxonomiesRead = components["schemas"]["TaxonomiesRead"]
type SyncState = components["schemas"]["SyncState"]

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

/** A capability profile with everything filled in but the past projects. */
export const profile: ProfileRead = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  org_id: ORG_ID,
  overview: "Systems integration and enterprise networking for public clients.",
  sectors: ["it"],
  geographies: ["BD"],
  keywords: ["networking"],
  annual_turnover: 200000000,
  turnover_currency: "BDT",
  turnover_year: 2025,
  years_in_business: 12,
  employee_count: 60,
  accepts_jv: true,
  completeness: 85,
  version: 3,
  updated_at: "2026-01-01T00:00:00Z",
  services: [
    {
      id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      name: "Network integration",
      position: 0,
    },
  ],
  past_projects: [],
  certifications: [
    {
      id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
      code: "ISO9001",
      label: "ISO 9001",
      issuer: null,
      valid_until: null,
    },
  ],
}

/** Mirrors the backend weights: every section but past projects is done. */
export const completeness: CompletenessRead = {
  score: 85,
  next_step: "Add your past projects.",
  sections: [
    { key: "overview", label: "Company overview", complete: true, weight: 25 },
    { key: "services", label: "Services", complete: true, weight: 25 },
    {
      key: "sectors",
      label: "Sectors and geographies",
      complete: true,
      weight: 15,
    },
    {
      key: "past_projects",
      label: "Past projects",
      complete: false,
      weight: 15,
    },
    { key: "turnover", label: "Annual turnover", complete: true, weight: 10 },
    {
      key: "certifications",
      label: "Certifications",
      complete: true,
      weight: 10,
    },
  ],
}

export const taxonomies: TaxonomiesRead = {
  sectors: [
    { value: "it", label: "It" },
    { value: "construction", label: "Construction" },
    { value: "healthcare", label: "Healthcare" },
  ],
  common_certifications: ["ISO 9001", "ISO 27001"],
}

/** Portals settled: nothing running, nothing to wait for, both pulled today. */
export const syncState: SyncState = {
  running: false,
  retry_after_seconds: 0,
  cooldown_seconds: 600,
  // A pool with notices in it: the default fixture is a working deployment, so
  // nothing auto-syncs unless a test asks for an empty one.
  pool_size: 146,
  auto_sync: true,
  queued: [],
  portals: [
    {
      id: "55555555-5555-4555-8555-555555555555",
      code: "egp_bd",
      name: "e-GP Bangladesh",
      enabled: true,
      health: "ok",
      running: false,
      last_run_at: "2026-09-11T08:00:00Z",
      last_success_at: "2026-09-11T08:00:00Z",
      last_status: "succeeded",
      last_notices_added: 3,
    },
    {
      id: "66666666-6666-4666-8666-666666666666",
      code: "wb",
      name: "World Bank procurement notices",
      enabled: true,
      health: "ok",
      running: false,
      last_run_at: "2026-09-11T08:00:01Z",
      last_success_at: "2026-09-11T08:00:01Z",
      last_status: "succeeded",
      last_notices_added: 0,
    },
  ],
}
