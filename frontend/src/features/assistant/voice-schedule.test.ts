import { describe, expect, it } from "vitest"

/**
 * The scheduling arithmetic behind live voice's tone.
 *
 * Placing each chunk at `max(now, end-of-last)` reads as obviously correct and
 * is the bug: the instant a chunk arrives later than real time, the schedule
 * has already passed, so it snaps to now — a silent gap, then the next buffer
 * starting mid-waveform. One is a click; at a twenty-millisecond cadence they
 * repeat at an audio rate, and that is a tone rather than clicking.
 *
 * Modelled here so the arithmetic is pinned without an AudioContext.
 */
const RATE = 24000
const TARGET_LEAD = 0.12
const MIN_LEAD = 0.02

function schedule(head: number, now: number, samples: number) {
  let underrun = false
  if (head / RATE < now + MIN_LEAD) {
    if (head > 0) underrun = true
    head = Math.ceil((now + TARGET_LEAD) * RATE)
  }
  return { startAt: head / RATE, head: head + samples, underrun }
}

describe("scheduling a live audio stream", () => {
  it("starts a fraction ahead rather than at this instant", () => {
    // Starting at `now` means the first render quantum has already gone.
    const first = schedule(0, 10, 480)

    expect(first.startAt).toBeGreaterThan(10)
    expect(first.startAt).toBeCloseTo(10 + TARGET_LEAD, 3)
  })

  it("plays chunks end to end with no gap between them", () => {
    let head = 0
    let now = 10
    const starts: number[] = []
    for (let i = 0; i < 50; i++) {
      const step = schedule(head, now, 480) // 20ms at 24kHz
      starts.push(step.startAt)
      head = step.head
      now += 0.02
    }

    for (let i = 1; i < starts.length; i++) {
      // Exactly 20ms apart, every time: contiguous, so no discontinuity.
      expect(starts[i] - starts[i - 1]).toBeCloseTo(0.02, 6)
    }
  })

  it("absorbs jitter that would previously have opened a gap", () => {
    // A chunk arriving 80ms late is well inside the lead.
    let { head } = schedule(0, 10, 480)
    const late = schedule(head, 10.1, 480)

    expect(late.underrun).toBe(false)
  })

  it("counts a genuine underrun rather than hiding it", () => {
    // Half a second of silence is past any lead; the schedule must re-establish
    // and say that it did.
    const { head } = schedule(0, 10, 480)
    const stalled = schedule(head, 10.6, 480)

    expect(stalled.underrun).toBe(true)
    expect(stalled.startAt).toBeCloseTo(10.6 + TARGET_LEAD, 3)
  })

  it("keeps an integer clock, so a long call does not drift", () => {
    // The old schedule accumulated `+= duration` in seconds. Over a stream of
    // thousands of chunks that rounding moves the boundary sub-sample.
    let head = 0
    let now = 10
    for (let i = 0; i < 20000; i++) {
      head = schedule(head, now, 480).head
      now += 0.02
    }

    expect(Number.isInteger(head)).toBe(true)
  })
})
