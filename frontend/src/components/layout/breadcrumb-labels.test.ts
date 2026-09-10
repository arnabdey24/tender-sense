import { describe, expect, it } from "vitest"

import { humanizeSegment } from "@/components/layout/breadcrumb-labels"

describe("breadcrumb segments", () => {
  it("uses a friendly label for known routes", () => {
    expect(humanizeSegment("dashboard")).toBe("Dashboard")
    expect(humanizeSegment("profile")).toBe("Capability profile")
  })

  it("does not title-case a record id", () => {
    // Regression: a tender detail page showed
    // "01a08644 403e 7ef2 8706 Babeb782048a" in the breadcrumb.
    expect(humanizeSegment("01a08644-403e-7ef2-8706-babeb782048a")).toBe("Detail")
  })

  it("still humanizes an unknown word", () => {
    expect(humanizeSegment("reset-password")).toBe("Reset Password")
  })
})
