import { describe, expect, it } from "vitest"

import { addsNothing, sourceLabel, sourceShort } from "@/features/tenders/format"

describe("addsNothing", () => {
  const title = "Development of Gazi Shah lane located in 16 no ward"

  it("suppresses a description that is the title verbatim", () => {
    expect(addsNothing(title, title)).toBe(true)
  })

  it("suppresses the title with portal filler appended", () => {
    expect(addsNothing(`${title} as per tender documents`, title)).toBe(true)
  })

  it("ignores casing and punctuation when comparing", () => {
    expect(addsNothing(`${title.toUpperCase()}.`, title)).toBe(true)
  })

  it("keeps prose that adds a real clause", () => {
    expect(
      addsNothing(
        `${title}, including drainage works and a six month defect liability period`,
        title
      )
    ).toBe(false)
  })

  it("keeps genuinely different prose", () => {
    expect(
      addsNothing("Sealed tenders are invited from eligible bidders.", title)
    ).toBe(false)
  })

  it("treats empty text as adding nothing", () => {
    expect(addsNothing(null, title)).toBe(true)
    expect(addsNothing("   ", title)).toBe(true)
  })

  it("compares against every baseline it is given", () => {
    expect(addsNothing("Tender - Single Lot", title, "Tender - Single Lot")).toBe(true)
  })
})

describe("source labels", () => {
  it("renders known codes as they are read, not as stored", () => {
    expect(sourceLabel("egp_bd")).toBe("e-GP")
    expect(sourceShort("wb")).toBe("WB")
  })

  it("makes an unknown code readable rather than dropping it", () => {
    expect(sourceLabel("new_portal")).toBe("new portal")
  })
})
