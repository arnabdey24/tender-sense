import { describe, expect, it } from "vitest"

/**
 * The chunk-boundary arithmetic behind live voice's worst artefact.
 *
 * A 16-bit sample is two bytes and a network chunk does not respect that. When
 * a chunk arrived with an odd byte count the spare byte was dropped, which put
 * every sample in the *next* chunk one byte out of phase — each one then built
 * from the high byte of one sample and the low byte of the next. That is not
 * noise: it is a loud periodic waveform in the middle of speech, which is what
 * a listener hears as a horn.
 *
 * This models the same carry the player performs, so the arithmetic is pinned
 * without standing up an AudioContext.
 */
function align(
  chunk: Uint8Array,
  pending: number | null
): { playable: Uint8Array; pending: number | null } {
  let bytes = chunk
  if (pending !== null) {
    bytes = new Uint8Array(chunk.length + 1)
    bytes[0] = pending
    bytes.set(chunk, 1)
  }
  let carry: number | null = null
  if (bytes.length % 2 === 1) {
    carry = bytes[bytes.length - 1]
    bytes = bytes.subarray(0, bytes.length - 1)
  }
  return { playable: bytes, pending: carry }
}

/** Read back the 16-bit samples a run of bytes decodes to. */
function samples(bytes: Uint8Array): number[] {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  return Array.from({ length: bytes.length / 2 }, (_, i) =>
    view.getInt16(i * 2, true)
  )
}

describe("aligning PCM across chunk boundaries", () => {
  it("never hands the player half a sample", () => {
    const first = align(new Uint8Array([1, 2, 3]), null)

    expect(first.playable.length % 2).toBe(0)
    expect(first.pending).toBe(3)
  })

  it("reunites a split sample with its other half", () => {
    // One stream, four samples, cut between the two bytes of the second.
    const whole = new Uint8Array([0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80])
    const expected = samples(whole)

    const a = align(whole.subarray(0, 3), null)
    const b = align(whole.subarray(3), a.pending)

    expect([...samples(a.playable), ...samples(b.playable)]).toEqual(expected)
    expect(b.pending).toBeNull()
  })

  it("would have shifted every later sample if the byte were dropped", () => {
    // The bug, stated as a test: drop the odd byte and the stream decodes to
    // different numbers entirely — which is the sound being reported.
    const whole = new Uint8Array([0x10, 0x20, 0x30, 0x40, 0x50, 0x60])
    const dropped = new Uint8Array([...whole.subarray(0, 2), ...whole.subarray(3)])

    expect(samples(dropped)).not.toEqual(samples(whole))
  })

  it("survives a run of odd chunks without drifting", () => {
    const whole = Uint8Array.from({ length: 30 }, (_, i) => i + 1)
    let pending: number | null = null
    const out: number[] = []

    for (let at = 0; at < whole.length; at += 3) {
      const step = align(whole.subarray(at, at + 3), pending)
      pending = step.pending
      out.push(...samples(step.playable))
    }

    expect(out).toEqual(samples(whole))
  })
})
