import { http, HttpResponse } from "msw"

import {
  companyResearch,
  completeness,
  decisions,
  errorEnvelope,
  invitationPreview,
  invitations,
  matches,
  members,
  notificationSettings,
  notifications,
  organization,
  profile,
  recipients,
  session,
  syncState,
  taxonomies,
  user,
} from "@/mocks/fixtures"

/**
 * Default handlers mirror the live API's success shapes. Individual tests
 * override the cases they care about with `server.use(...)`.
 */
export const handlers = [
  http.get("*/api/v1/assistant/capabilities", () =>
    HttpResponse.json({
      enabled: true,
      voice_enabled: false,
      mode: "demo",
      voice_max_seconds: 600,
    })
  ),
  http.get("*/api/v1/assistant/conversations", () => HttpResponse.json([])),
  http.get("*/api/v1/health/live", () => HttpResponse.json({ status: "ok" })),
  http.get("*/api/v1/sources/sync", () => HttpResponse.json(syncState)),
  http.post("*/api/v1/sources/sync", () =>
    HttpResponse.json({ ...syncState, queued: ["egp_bd", "wb"], running: true })
  ),

  // Signed out by default: the silent refresh finds no cookie.
  http.post("*/api/v1/auth/refresh", () =>
    HttpResponse.json(errorEnvelope("unauthenticated", "No active session."), {
      status: 401,
    })
  ),

  http.post("*/api/v1/auth/login", () => HttpResponse.json(session())),
  http.get("*/api/v1/auth/me", () => HttpResponse.json(session())),
  http.patch("*/api/v1/users/me", async ({ request }) =>
    HttpResponse.json({ ...user, ...((await request.json()) as object) })
  ),
  http.post("*/api/v1/auth/logout", () =>
    HttpResponse.json({ message: "Signed out." })
  ),
  http.post("*/api/v1/auth/logout-all", () =>
    HttpResponse.json({ message: "Signed out everywhere." })
  ),
  http.post("*/api/v1/auth/register", () =>
    HttpResponse.json({ user, verification_email_sent: true }, { status: 201 })
  ),
  http.post("*/api/v1/auth/verify-email", () => HttpResponse.json(session())),
  http.post("*/api/v1/auth/resend-verification", () =>
    HttpResponse.json({ message: "Verification email sent." })
  ),
  http.post("*/api/v1/auth/forgot-password", () =>
    HttpResponse.json({
      message: "If the account exists, a link is on its way.",
    })
  ),
  http.post("*/api/v1/auth/reset-password", () => HttpResponse.json(session())),
  http.post("*/api/v1/auth/change-password", () =>
    HttpResponse.json({ message: "Password changed." })
  ),
  http.post("*/api/v1/auth/switch-org", () => HttpResponse.json(session())),

  http.post("*/api/v1/orgs", () =>
    HttpResponse.json(organization, { status: 201 })
  ),
  http.get("*/api/v1/notifications", ({ request }) => {
    const unreadOnly =
      new URL(request.url).searchParams.get("unread_only") === "true"
    return HttpResponse.json(
      unreadOnly ? notifications.filter((n) => !n.read) : notifications
    )
  }),
  http.get("*/api/v1/notifications/unread-count", () =>
    HttpResponse.json({ unread: notifications.filter((n) => !n.read).length })
  ),
  http.post("*/api/v1/notifications/read-all", () =>
    HttpResponse.json({ unread: 0 })
  ),
  http.post(
    "*/api/v1/notifications/:id/read",
    () => new HttpResponse(null, { status: 204 })
  ),
  http.get("*/api/v1/notification-settings", () =>
    HttpResponse.json(notificationSettings)
  ),
  http.put("*/api/v1/notification-settings", async ({ request }) =>
    HttpResponse.json({
      ...notificationSettings,
      ...((await request.json()) as object),
    })
  ),
  http.get("*/api/v1/notification-recipients", () =>
    HttpResponse.json(recipients)
  ),

  http.get("*/api/v1/orgs/current", () => HttpResponse.json(organization)),
  http.patch("*/api/v1/orgs/current", () => HttpResponse.json(organization)),
  http.get("*/api/v1/orgs/current/members", () =>
    HttpResponse.json({
      items: members,
      page: 1,
      page_size: 50,
      total: members.length,
    })
  ),
  http.patch("*/api/v1/orgs/current/members/:userId", () =>
    HttpResponse.json(members[1])
  ),
  http.delete(
    "*/api/v1/orgs/current/members/:userId",
    () => new HttpResponse(null, { status: 204 })
  ),
  http.get("*/api/v1/orgs/current/invitations", () =>
    HttpResponse.json(invitations)
  ),
  http.post("*/api/v1/orgs/current/invitations", () =>
    HttpResponse.json(invitations[0], { status: 201 })
  ),
  http.post("*/api/v1/orgs/current/invitations/:id/resend", () =>
    HttpResponse.json(invitations[0])
  ),
  http.delete(
    "*/api/v1/orgs/current/invitations/:id",
    () => new HttpResponse(null, { status: 204 })
  ),

  // The signed-in shell mounts on every route, so its two background queries
  // answer everywhere rather than only on the pages that display them.
  http.get("*/api/v1/tenders", () =>
    HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 })
  ),
  http.get("*/api/v1/matches/stats", () =>
    HttpResponse.json({
      total: matches.length,
      by_grade: { S: 1, B: 1 },
      by_eligibility: { eligible: 1, needs_verification: 1 },
      by_recommendation: { bid: 1, hold: 1 },
      by_urgency: { normal: 1, high: 1 },
      closing_within_7_days: 1,
      new_today: 1,
    })
  ),
  http.get("*/api/v1/matches/today", () =>
    HttpResponse.json({
      items: matches,
      page: 1,
      page_size: 20,
      total: matches.length,
    })
  ),
  http.get("*/api/v1/matches", () =>
    HttpResponse.json({
      items: matches,
      page: 1,
      page_size: 20,
      total: matches.length,
    })
  ),
  http.get("*/api/v1/decisions", () =>
    HttpResponse.json({
      items: decisions,
      page: 1,
      page_size: 20,
      total: decisions.length,
    })
  ),

  http.get("*/api/v1/profile", () => HttpResponse.json(profile)),
  http.put("*/api/v1/profile", async ({ request }) =>
    HttpResponse.json({ ...profile, ...((await request.json()) as object) })
  ),
  http.get("*/api/v1/profile/completeness", () =>
    HttpResponse.json(completeness)
  ),
  http.get("*/api/v1/taxonomies", () => HttpResponse.json(taxonomies)),
  http.post("*/api/v1/profile/services", async ({ request }) =>
    HttpResponse.json(
      {
        id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        ...((await request.json()) as object),
      },
      { status: 201 }
    )
  ),
  http.delete(
    "*/api/v1/profile/services/:id",
    () => new HttpResponse(null, { status: 204 })
  ),
  http.post("*/api/v1/profile/projects", async ({ request }) =>
    HttpResponse.json(
      {
        id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        ...((await request.json()) as object),
      },
      { status: 201 }
    )
  ),
  http.delete(
    "*/api/v1/profile/projects/:id",
    () => new HttpResponse(null, { status: 204 })
  ),
  http.post("*/api/v1/profile/certifications", async ({ request }) =>
    HttpResponse.json(
      {
        id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
        code: "ISO9001",
        ...((await request.json()) as object),
      },
      { status: 201 }
    )
  ),
  http.delete(
    "*/api/v1/profile/certifications/:id",
    () => new HttpResponse(null, { status: 204 })
  ),
  http.post("*/api/v1/profile/rematch", () =>
    HttpResponse.json({ enqueued: true, job_id: "job-1", reason: "manual" })
  ),

  http.post("*/api/v1/ai/research-company", async ({ request }) => {
    const { url } = (await request.json()) as { url: string }
    // Mirrors the backend: an address that cannot be read is an error, never
    // a confidently invented company.
    if (url.includes("unreadable") || url.includes(".invalid")) {
      return HttpResponse.json(
        errorEnvelope("research_failed", "We could not read that website."),
        { status: 502 }
      )
    }
    return HttpResponse.json({ ...companyResearch, retrieved_url: url })
  }),
  http.post("*/api/v1/ai/improve-text", async ({ request }) => {
    const { text } = (await request.json()) as { text: string }
    return HttpResponse.json({ text: `${text.trim()} (tightened)`, note: "" })
  }),

  http.get("*/api/v1/invitations/:token", () =>
    HttpResponse.json(invitationPreview)
  ),
  http.post("*/api/v1/invitations/:token/accept", () =>
    HttpResponse.json(members[1])
  ),
]
