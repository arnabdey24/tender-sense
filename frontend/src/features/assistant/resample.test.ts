import { describe, expect, it } from "vitest"

import { StreamResampler } from "./resample"

/**
 * The defect these pin is a seam, not a sound.
 *
 * A resampler that restarts at every chunk boundary still produces plausible
 * audio — each chunk on its own is correct. What it produces is a small error
 * that repeats with the chunk cadence, which at fifty chunks a second is a
 * tone rather than noise. So the assertion that matters is not "is this chunk
 * right" but "is chunked output the same as converting the whole stream at
 * once", which is what a listener actually hears.
 */

function tone(samples: number, hz: number, rate: number, from = 0): Float32Array {
  const out = new Float32Array(samples)
  for (let i = 0; i < samples; i++) {
    out[i] = Math.sin((2 * Math.PI * hz * (from + i)) / rate)
  }
  return out
}

function pushAll(r: StreamResampler, chunks: Float32Array[]): Float32Array {
  const parts = chunks.map((c) => Array.from(r.push(c)))
  return Float32Array.from(parts.flat())
}

describe("StreamResampler", () => {
  it("is the identity when the rates already match", () => {
    const r = new StreamResampler(24000, 24000)
    const input = tone(480, 1000, 24000)
    expect(r.passthrough).toBe(true)
    expect(Array.from(r.push(input))).toEqual(Array.from(input))
  })

  /*
    44100 is the case that can actually fail, and the reason this is spelled
    out: at 48000 the ratio is exactly 2, so with even chunk lengths the phase
    lands back on zero at every boundary and a resampler that restarts each
    chunk is indistinguishable from one that does not. A test written only
    against 48000 passes with the defect fully present — it was, before this
    comment existed. 44100 gives a step of 0.544, which drifts.
  */
  it.each([
    [48000, "the common hardware rate"],
    [44100, "the rate whose phase actually drifts"],
    [22050, "a rate below the stream's own"],
  ])("converting in chunks matches the whole stream at %i (%s)", (rate) => {
    const TOTAL = 4800 // 200ms at 24k
    const CHUNK = 480 // the cadence live voice actually arrives at
    const whole = tone(TOTAL, 1000, 24000)

    const chunks: Float32Array[] = []
    for (let i = 0; i < TOTAL; i += CHUNK) chunks.push(whole.slice(i, i + CHUNK))

    const chunked = pushAll(new StreamResampler(24000, rate), chunks)
    const once = new StreamResampler(24000, rate).push(whole)

    // Length alone catches a restart that duplicates or drops a sample per
    // chunk, which is ten samples over this stream.
    expect(Math.abs(chunked.length - once.length)).toBeLessThanOrEqual(1)

    const n = Math.min(chunked.length, once.length)
    let worst = 0
    for (let i = 0; i < n; i++) {
      worst = Math.max(worst, Math.abs(chunked[i] - once[i]))
    }
    expect(worst).toBeLessThan(1e-6)
  })

  it("leaves no discontinuity where two chunks meet", () => {
    /*
      A seam shows up as a step between neighbouring output samples that is
      far larger than the signal's own slope. Restarting the phase each chunk
      produces exactly that, about fifty times a second.
    */
    const CHUNK = 480
    const chunks = Array.from({ length: 10 }, (_, c) =>
      tone(CHUNK, 1000, 24000, c * CHUNK)
    )
    const out = pushAll(new StreamResampler(24000, 44100), chunks)

    /*
      Both directions are a seam. A restart that repeats the previous sample
      leaves a step of zero where the tone should still be moving; one that
      skips ahead leaves a step larger than the tone's own slope. A 1 kHz tone
      at 44.1 kHz moves about 0.142 per sample at the steepest and never
      flattens, so both bounds are real.
    */
    let worstStep = 0
    let flattest = 1
    for (let i = 1; i < out.length; i++) {
      const step = Math.abs(out[i] - out[i - 1])
      worstStep = Math.max(worstStep, step)
      // Away from the tone's own peaks, where it genuinely flattens.
      if (Math.abs(out[i]) < 0.9) flattest = Math.min(flattest, step)
    }
    expect(worstStep).toBeLessThan(0.16)
    expect(flattest).toBeGreaterThan(0)
  })

  it("keeps the stream's duration across many chunks", () => {
    const CHUNK = 480
    const COUNT = 100
    const r = new StreamResampler(24000, 48000)
    let produced = 0
    for (let c = 0; c < COUNT; c++) {
      produced += r.push(tone(CHUNK, 440, 24000, c * CHUNK)).length
    }
    // Two output samples per input sample, give or take the final partial one.
    expect(produced).toBeGreaterThan(CHUNK * COUNT * 2 - 4)
    expect(produced).toBeLessThanOrEqual(CHUNK * COUNT * 2)
  })

  it("never returns a sample outside full scale", () => {
    const loud = new Float32Array(480).fill(1)
    loud[10] = -1
    const out = new StreamResampler(24000, 48000).push(loud)
    for (const s of out) expect(Math.abs(s)).toBeLessThanOrEqual(1)
  })

  it("forgets the phase of an utterance that was interrupted", () => {
    const r = new StreamResampler(24000, 48000)
    r.push(tone(480, 1000, 24000))
    r.reset()
    const after = r.push(tone(480, 1000, 24000))
    const fresh = new StreamResampler(24000, 48000).push(tone(480, 1000, 24000))
    expect(Array.from(after)).toEqual(Array.from(fresh))
  })

  it("an empty chunk is not an error", () => {
    const r = new StreamResampler(24000, 48000)
    expect(r.push(new Float32Array(0)).length).toBe(0)
  })
})
