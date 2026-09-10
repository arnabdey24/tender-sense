import { describe, expect, it } from "vitest"

import { session } from "@/mocks/fixtures"
import { describeViolations, findViolations } from "@/test/a11y"
import { renderRoute } from "@/test/render"

/**
 * An automated pass catches the mechanical half of accessibility — unlabelled
 * controls, broken heading order, form fields with no name. It cannot judge
 * whether a label is *useful*, so it is a floor rather than a verdict.
 *
 * Colour contrast is excluded because jsdom has no layout engine and reports
 * every element as failing; that check belongs in a browser run.
 */
const AUTHED_PAGES = [
  "/app/dashboard",
  "/app/notifications",
  "/app/settings",
  "/app/settings/notifications",
  "/app/settings/sources",
]

const PUBLIC_PAGES = ["/", "/login", "/register", "/forgot-password"]

describe("accessibility", () => {
  it.each(PUBLIC_PAGES)(
    "%s has no automatically detectable violations",
    async (path) => {
      const { container } = await renderRoute(path)

      const violations = await findViolations(container)

      expect(violations, describeViolations(violations)).toEqual([])
    }
  )

  it.each(AUTHED_PAGES)(
    "%s has no automatically detectable violations",
    async (path) => {
      const { container } = await renderRoute(path, { session: session() })

      const violations = await findViolations(container)

      expect(violations, describeViolations(violations)).toEqual([])
    }
  )
})
