import { http, HttpResponse } from "msw"

import {
  errorEnvelope,
  invitationPreview,
  invitations,
  members,
  notificationSettings,
  notifications,
  organization,
  recipients,
  session,
  user,
} from "@/mocks/fixtures"

/**
 * Default handlers mirror the live API's success shapes. Individual tests
 * override the cases they care about with `server.use(...)`.
 */
export const handlers = [
  http.get("*/api/v1/assistant/capabilities", () => HttpResponse.json({ enabled: true, voice_enabled: false, mode: "demo", voice_max_seconds: 600 })),
  http.get("*/api/v1/assistant/conversations", () => HttpResponse.json([])),
  http.get("*/api/v1/health/live", () => HttpResponse.json({ status: "ok" })),

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

  http.get("*/api/v1/invitations/:token", () =>
    HttpResponse.json(invitationPreview)
  ),
  http.post("*/api/v1/invitations/:token/accept", () =>
    HttpResponse.json(members[1])
  ),
]
