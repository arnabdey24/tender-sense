import { expect, test } from "@playwright/test"

test("landing page renders the TenderSense heading", async ({ page }) => {
  await page.goto("/")
  await expect(
    page.getByRole("heading", { level: 1, name: "TenderSense" })
  ).toBeVisible()
})

test("sign-in page offers password and Google sign-in", async ({ page }) => {
  await page.goto("/login")
  await expect(page.getByLabel("Email")).toBeVisible()
  await expect(page.getByLabel("Password")).toBeVisible()
  await expect(page.getByText("Sign in with Google")).toBeVisible()
  await expect(
    page.getByRole("link", { name: "Create an account" })
  ).toBeVisible()
})

test("an unauthenticated visitor is redirected from /app to /login", async ({
  page,
}) => {
  await page.goto("/app/dashboard")
  await expect(page).toHaveURL(/\/login/)
})

/**
 * Full identity journey. Skipped by default: it needs a live backend plus a way
 * to read the verification token out of the outbound mail (MailHog/Mailpit or a
 * test-only endpoint). Unskip once the harness exposes that, and run with
 * `VITE_API_PROXY_TARGET` pointed at the API.
 */
test.skip("register → verify → create org → dashboard", async ({ page }) => {
  const email = `e2e+${Date.now()}@example.com`

  await page.goto("/register")
  await page.getByLabel("Full name").fill("E2E Tester")
  await page.getByLabel("Work email").fill(email)
  await page.getByLabel("Password").fill("Sup3rSecret!pass")
  await page.getByRole("button", { name: "Create account" }).click()
  await expect(page.getByText("Check your inbox")).toBeVisible()

  // Requires a mail sink: fetch the newest verification token for `email`.
  const token = "REPLACE_WITH_TOKEN_FROM_MAIL_SINK"

  await page.goto(`/verify-email?token=${token}`)
  await expect(page).toHaveURL(/\/onboarding/)

  await page.getByLabel("Organization name").fill("E2E Engineering")
  await page.getByRole("button", { name: "Create organization" }).click()

  await expect(page).toHaveURL(/\/app\/dashboard/)
  await expect(page.getByText("E2E Engineering")).toBeVisible()
})

/** Invitation acceptance also needs a live backend and a real invite token. */
test.skip("invited user accepts and lands in the org", async ({ page }) => {
  const token = "REPLACE_WITH_INVITATION_TOKEN"

  await page.goto(`/invite/accept?token=${token}`)
  await expect(page.getByRole("tab", { name: "Sign in" })).toBeVisible()
  await page.getByLabel("Email").fill("invitee@example.com")
  await page.getByLabel("Password").fill("Sup3rSecret!pass")
  await page.getByRole("button", { name: "Sign in" }).click()

  await page.getByRole("button", { name: /^Join / }).click()
  await expect(page).toHaveURL(/\/app\/dashboard/)
})
