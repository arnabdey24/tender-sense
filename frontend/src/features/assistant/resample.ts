/**
 * Rate conversion for a stream that arrives in chunks.
 *
 * The point of this module is not the interpolation, which is ordinary. It is
 * that the read head survives a chunk boundary.
 *
 * Live voice arrives as twenty-millisecond chunks of 24 kHz PCM, and for a
 * long time each one was handed to the browser as its own `AudioBuffer` tagged
 * 24 kHz inside a context running at 48 kHz. The browser then resampled every
 * chunk *in isolation* — interpolating from its first sample to its last with
 * no knowledge of the chunk before it, and restarting the phase each time.
 * Rendered offline against a pure tone, that costs 0.43% RMS error into 48 kHz
 * and 0.45% into 44.1 kHz, and exactly zero when the rates match.
 *
 * A constant 0.4% error would be hiss. This one is not constant: it repeats
 * with the chunk cadence, about fifty times a second, which makes it a
 * periodic waveform sitting under the speech. That is why it was heard as a
 * horn rather than as noise, and why chasing it as "a gap in the schedule"
 * fixed a real bug without silencing it.
 *
 * So the conversion happens once, here, with `pos` and the previous chunk's
 * last sample carried across the call.
 */
export class StreamResampler {
  /** Read position, in source samples, relative to the current input array. */
  private pos = 0
  /** The previous chunk's last sample, so the seam has both sides to read. */
  private tail: number | null = null

  private readonly from: number
  private readonly to: number

  constructor(from: number, to: number) {
    this.from = from
    this.to = to
  }

  /** True when the rates match and conversion would be the identity. */
  get passthrough(): boolean {
    return this.from === this.to
  }

  push(incoming: Float32Array): Float32Array {
    if (this.passthrough) return incoming
    if (incoming.length === 0) return incoming

    // The previous chunk's last sample sits at index 0, so a read head that
    // landed between the two still has a sample on either side of it. `pos`
    // was stored as a distance past that sample, which is this array's
    // coordinate system already.
    let source = incoming
    if (this.tail !== null) {
      source = new Float32Array(incoming.length + 1)
      source[0] = this.tail
      source.set(incoming, 1)
    }

    const step = this.from / this.to
    const out = new Float32Array(Math.ceil((source.length - this.pos) / step))
    let written = 0
    let pos = this.pos
    while (pos + 1 < source.length) {
      const i = Math.floor(pos)
      const t = pos - i
      const value = source[i] * (1 - t) + source[i + 1] * t
      // Interpolation can overshoot a full-scale sample, and a sample that
      // wraps is a click rather than a loud one.
      out[written++] = value > 1 ? 1 : value < -1 ? -1 : value
      pos += step
    }

    this.tail = source[source.length - 1]
    this.pos = pos - (source.length - 1)
    return out.subarray(0, written)
  }

  /**
   * Forget the stream.
   *
   * An interruption throws away the rest of an utterance, so the phase and the
   * held sample belong to nothing — carrying them into whatever is said next
   * would start that stream out of phase.
   */
  reset() {
    this.pos = 0
    this.tail = null
  }
}
