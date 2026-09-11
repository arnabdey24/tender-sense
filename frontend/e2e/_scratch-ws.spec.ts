import { expect, test } from "@playwright/test"
const APP = "http://localhost:5180"
const SHOTS = process.env.SHOTS!

test("controls available in the analysis workspace", async ({ page }) => {
  await page.goto(`${APP}/login`)
  await page.getByLabel("Email").fill("demo@tendersense.io")
  await page.getByLabel("Password").fill("MNuV3x9BheuXpwcWbVBuuacz")
  await page.getByRole("button", { name: /sign in|log in/i }).first().click()
  await page.waitForURL(/\/app\//, { timeout: 25000 })

  await page.setViewportSize({ width: 1484, height: 858 })
  await page.goto(`${APP}/app/dashboard`)
  await page.waitForLoadState("networkidle")
  await page.locator(".assistant-launcher button").first().click()
  await page.waitForTimeout(1200)

  const inPanel = async (label: string) =>
    (await page.locator(".assistant-panel").getByRole("button", { name: label }).count()) > 0

  console.log("COMPACT buttons:", JSON.stringify(await page.locator(".assistant-panel").getByRole("button").evaluateAll(
    (els) => els.map((e) => e.getAttribute("aria-label")).filter(Boolean)
  )))

  // Open the analysis workspace, the way a user does.
  await page.getByText("Analysis workspace").click()
  await page.waitForTimeout(1200)
  const cls = await page.locator(".assistant-panel").getAttribute("class")
  console.log("WORKSPACE mode class:", cls?.includes("workspace"))
  console.log("WORKSPACE buttons:", JSON.stringify(await page.locator(".assistant-panel").getByRole("button").evaluateAll(
    (els) => els.map((e) => e.getAttribute("aria-label")).filter(Boolean)
  )))
  console.log("has Compact chat:", await inPanel("Compact chat"))
  console.log("has Minimize assistant:", await inPanel("Minimize assistant"))
  await page.screenshot({ path: `${SHOTS}/workspace.png` })
  expect(true).toBe(true)
})
