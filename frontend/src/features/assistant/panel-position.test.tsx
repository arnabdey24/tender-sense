import { describe, expect, it } from "vitest"

import { cn } from "@/lib/utils"

/**
 * The dialog centres itself; the assistant panel does not want to be centred.
 *
 * `index.css` used to undo the centring in a rule that sits in the same
 * `@layer utilities` as the utilities it was overriding. Same layer, same
 * specificity, so source order decides — and Tailwind emits utilities last in a
 * production build while the dev server happened to emit them first. The panel
 * was therefore correct in development and, on the deployed site only, shifted
 * by half its own size: 210px left, 370px up, its header off the top of the
 * window. Nothing in the test suite could see it, because the suite never ran
 * the built CSS.
 *
 * Naming the conflict in the class list takes the cascade out of it entirely:
 * the merger drops the centring classes before they reach the DOM, so there is
 * nothing left to win or lose an ordering. This pins that.
 */
const DIALOG_BASE =
  "fixed top-1/2 left-1/2 z-50 w-full -translate-x-1/2 -translate-y-1/2 rounded-xl"

const PANEL = "assistant-panel top-auto left-auto translate-none"

describe("the assistant panel's position", () => {
  it("drops the dialog's centring classes rather than fighting them in CSS", () => {
    const result = cn(DIALOG_BASE, PANEL)

    expect(result).not.toContain("-translate-x-1/2")
    expect(result).not.toContain("-translate-y-1/2")
    expect(result).not.toContain("top-1/2")
    expect(result).not.toContain("left-1/2")
  })

  it("keeps the classes that put it in the corner", () => {
    const result = cn(DIALOG_BASE, PANEL)

    expect(result).toContain("translate-none")
    expect(result).toContain("top-auto")
    expect(result).toContain("left-auto")
    expect(result).toContain("fixed")
  })
})
