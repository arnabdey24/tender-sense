import { apiUrl } from "@/lib/api/base"
import { StreamResampler } from "./resample"
import { assistantFetch } from "./api"
import { eventSchema, type AssistantEvent, type Language } from "./schemas"

export type VoiceState =
  | "idle"
  | "permission"
  | "connecting"
  | "listening"
  | "processing"
  | "speaking"
  | "muted"
  | "error"

/**
 * Gemini Live speaks at 24 kHz, and so does the context that plays it.
 *
 * Asking for the rate is the whole fix for the buzz. A default `AudioContext`
 * runs at the hardware rate — 48000 on every machine tested — and each 24 kHz
 * chunk was then resampled by the browser *in isolation*, with the
 * interpolator restarting at every chunk boundary. Rendered offline against a
 * pure tone that costs 0.43% RMS error into 48000 and 0.45% into 44100, and
 * exactly zero when the rates match.
 *
 * Which is why it was heard as a horn rather than as noise: the error is
 * deterministic and repeats with the chunk cadence, about fifty times a
 * second, so it is a periodic waveform under the speech rather than hiss. The
 * same interpolation is why the voice sounded harsh — upsampling without an
 * anti-imaging filter leaves images in the top octave, where sibilance lives.
 */
const OUTPUT_RATE = 24000

/**
 * What the microphone is captured at, in its own context.
 *
 * One context served both directions, so whatever rate it ran at, something
 * was being resampled. Separating them means the capture worklet's step is
 * exactly 1 and the only conversion left — the microphone's own rate to this
 * one — is done by the platform's resampler rather than by linear
 * interpolation in a worklet.
 */
const INPUT_RATE = 16000

/**
 * A context at the rate asked for, or the best the browser will give.
 *
 * Safari has historically thrown `NotSupportedError` for an explicit rate. A
 * buzz is a bad experience; voice refusing to start at all is a worse one, so
 * a browser that will not take the hint gets the default context and the
 * resampler picks up the difference.
 */
function contextAt(rate: number): AudioContext {
  try {
    return new AudioContext({ sampleRate: rate })
  } catch {
    return new AudioContext()
  }
}

/** Where the schedule is aimed when it has to be re-established. */
const TARGET_LEAD = 0.12

/** Below this, the next chunk cannot be placed without a gap. */
const MIN_LEAD = 0.02

export class VoiceSession {
  private socket?: WebSocket
  private stream?: MediaStream
  private audio?: AudioContext
  private input?: AudioContext
  /** Only does anything when a browser refused a 24 kHz context. */
  private resampler?: StreamResampler
  /** Half a sample, waiting for the byte that completes it. */
  private pendingByte: number | null = null
  private capture?: AudioWorkletNode
  private sources = new Set<AudioBufferSourceNode>()
  /**
   * The end of scheduled audio, counted in samples rather than seconds.
   *
   * Seconds accumulate floating-point error: a stream is thousands of chunks,
   * and `+= buffer.duration` on each one drifts the schedule sub-sample until
   * it re-snaps. Samples are integers and 24,000 of them is exactly a second.
   */
  private playHead = 0
  /** Times the stream arrived later than it could be played. */
  private underruns = 0
  private stopped = false
  private muted = false
  private speakerMuted = false
  private outputGain?: GainNode
  private monitor?: ReturnType<typeof setInterval>
  private speaking = false
  private started = Date.now()
  private onState: (state: VoiceState, level?: number) => void
  private onEvent: (event: AssistantEvent) => void
  private onError: (message: string) => void
  constructor(
    onState: (state: VoiceState, level?: number) => void,
    onEvent: (event: AssistantEvent) => void,
    onError: (message: string) => void
  ) {
    this.onState = onState
    this.onEvent = onEvent
    this.onError = onError
  }

  async start(conversationId: string, language: Language) {
    try {
      if (!navigator.mediaDevices?.getUserMedia)
        throw new Error(
          "Microphone access requires HTTPS and a supported browser."
        )
      this.onState("permission")
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      })
      if (this.stopped) {
        this.stream.getTracks().forEach((track) => track.stop())
        return
      }
      // Two contexts, each at the rate of the stream it carries, so neither
      // direction is resampled by the browser a chunk at a time.
      this.audio = contextAt(OUTPUT_RATE)
      this.input = contextAt(INPUT_RATE)
      await Promise.all([this.audio.resume(), this.input.resume()])
      await this.input.audioWorklet.addModule("/assistant-audio.js")
      if (this.stopped) return
      this.onState("connecting")
      const response = await assistantFetch(
        `/conversations/${conversationId}/voice-ticket`,
        { method: "POST" }
      )
      const { ticket } = (await response.json()) as { ticket: string }
      if (this.stopped) return
      const url = new URL(apiUrl("/api/v1/assistant/voice"))
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
      this.socket = new WebSocket(url)
      this.socket.onopen = () =>
        this.socket?.send(JSON.stringify({ ticket, language }))
      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(String(event.data)) as Record<string, unknown>
          if (data.type === "ready") {
            this.captureAudio()
            this.onState("listening")
            return
          }
          if (data.type === "audio") {
            this.play(String(data.audio))
            return
          }
          if (data.type === "interrupted") {
            this.clearPlayback()
            this.onState(this.muted ? "muted" : "listening")
          }
          if (data.type === "error") {
            this.fail(
              String(
                (data.data as Record<string, unknown>)?.message ??
                  "Voice connection failed."
              )
            )
            return
          }
          this.onEvent(eventSchema.parse(data))
        } catch {
          this.fail("The voice connection returned an invalid response.")
        }
      }
      this.socket.onerror = () =>
        this.fail("Voice connection failed. You can continue by typing.")
      this.socket.onclose = () => {
        if (!this.stopped)
          this.fail(
            "Voice ended or the connection was lost. Your saved conversation is available; start voice again to reconnect."
          )
      }
    } catch (error) {
      this.fail(
        error instanceof Error
          ? error.message
          : "Could not access the microphone."
      )
    }
  }

  private captureAudio() {
    if (!this.audio || !this.input || !this.stream || this.stopped) return
    const source = this.input.createMediaStreamSource(this.stream)
    this.capture = new AudioWorkletNode(this.input, "assistant-capture")
    const silent = this.input.createGain()
    silent.gain.value = 0
    source.connect(this.capture).connect(silent).connect(this.input.destination)
    this.outputGain = this.audio.createGain()
    this.outputGain.connect(this.audio.destination)
    this.capture.port.onmessage = (
      event: MessageEvent<{ audio: ArrayBuffer; level: number }>
    ) => {
      if (
        this.stopped ||
        this.muted ||
        this.socket?.readyState !== WebSocket.OPEN
      )
        return
      if (this.socket.bufferedAmount > 128000) {
        this.fail(
          "Your connection is too slow for live voice. Please reconnect or use text."
        )
        return
      }
      this.socket.send(event.data.audio)
      if (!this.speaking)
        this.onState("listening", Math.min(event.data.level * 8, 1))
    }
    this.monitor = setInterval(() => {
      if (
        this.audio &&
        this.speaking &&
        this.audio.currentTime >= this.playHead / this.audio.sampleRate
      ) {
        this.speaking = false
        this.onState(this.muted ? "muted" : "listening", 0)
      }
    }, 100)
  }

  private play(encoded: string) {
    if (!this.audio || !this.outputGain || this.stopped) return
    const raw = atob(encoded)
    const arrived = Uint8Array.from(raw, (c) => c.charCodeAt(0))

    /*
     * A 16-bit sample is two bytes, and a chunk boundary does not respect that.
     *
     * When a chunk arrives with an odd number of bytes the last byte is half a
     * sample. Dropping it puts every sample in the *next* chunk one byte out of
     * phase — each one then built from the high byte of one sample and the low
     * byte of the next, which is not noise but a loud periodic waveform. That
     * is the horn: a sustained buzz in the middle of speech, on a stream that
     * is otherwise clean.
     *
     * So the odd byte waits for the byte that completes it.
     */
    let bytes = arrived
    if (this.pendingByte !== null) {
      bytes = new Uint8Array(arrived.length + 1)
      bytes[0] = this.pendingByte
      bytes.set(arrived, 1)
      this.pendingByte = null
    }
    if (bytes.length % 2 === 1) {
      this.pendingByte = bytes[bytes.length - 1]
      bytes = bytes.subarray(0, bytes.length - 1)
    }
    // An empty chunk is not an error, but `createBuffer(1, 0, …)` throws.
    if (bytes.length === 0) return

    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
    const incoming = new Float32Array(bytes.length / 2)
    for (let i = 0; i < incoming.length; i++) {
      incoming[i] = view.getInt16(i * 2, true) / 32768
    }

    this.resampler ??= new StreamResampler(OUTPUT_RATE, this.audio.sampleRate)
    const samples = this.resampler.push(incoming)
    if (samples.length === 0) return

    const buffer = this.audio.createBuffer(
      1,
      samples.length,
      this.audio.sampleRate
    )
    const channel = buffer.getChannelData(0)
    channel.set(samples)
    let energy = 0
    for (let i = 0; i < channel.length; i++) energy += channel[i] ** 2
    if (this.playHead / this.audio.sampleRate - this.audio.currentTime > 30) {
      this.fail("Audio playback fell behind. Please restart voice.")
      return
    }
    const source = this.audio.createBufferSource()
    source.buffer = buffer
    source.connect(this.outputGain)
    this.sources.add(source)
    source.onended = () => this.sources.delete(source)

    /*
     * A lead, so ordinary network jitter cannot open a gap.
     *
     * Scheduling each chunk at `max(currentTime, end-of-last)` sounds correct
     * and is the whole bug: the moment a chunk arrives later than real time —
     * which on any real connection is most of them — the schedule has already
     * passed, so it snaps to now. That leaves a silent gap and starts the next
     * buffer mid-waveform. One of those is a click. At a twenty-millisecond
     * chunk cadence they repeat tens of times a second, and a discontinuity
     * repeating at an audio rate is not heard as clicking. It is heard as a
     * tone — which is the horn.
     *
     * So the stream is played a fraction behind where it arrives, and the
     * fraction absorbs the jitter. The cost is 120ms of latency on a spoken
     * reply, which nobody can hear; the cost of not having it is audible to
     * everybody.
     */
    const now = this.audio.currentTime
    if (this.playHead / this.audio.sampleRate < now + MIN_LEAD) {
      if (this.playHead > 0) this.underruns += 1
      this.playHead = Math.ceil((now + TARGET_LEAD) * this.audio.sampleRate)
    }
    source.start(this.playHead / this.audio.sampleRate)
    this.playHead += buffer.length
    this.speaking = true
    this.onState(
      "speaking",
      Math.min(Math.sqrt(energy / channel.length) * 5, 1)
    )
  }

  sendText(text: string) {
    this.clearPlayback()
    this.socket?.send(JSON.stringify({ type: "text", text }))
    this.onState("processing")
  }
  setMuted(muted: boolean) {
    this.muted = muted
    this.stream?.getAudioTracks().forEach((track) => {
      track.enabled = !muted
    })
    if (muted && this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(JSON.stringify({ type: "mute" }))
    this.onState(muted ? "muted" : "listening", 0)
  }
  setSpeakerMuted(muted: boolean) {
    this.speakerMuted = muted
    if (this.outputGain) this.outputGain.gain.value = this.speakerMuted ? 0 : 1
  }
  private clearPlayback() {
    for (const source of this.sources) {
      try {
        source.stop()
      } catch {
        /* Already ended. */
      }
    }
    this.sources.clear()
    this.playHead = 0
    this.speaking = false
    // An interruption discards the rest of that utterance, so a half sample
    // held from it has nothing to complete it — carrying it into whatever is
    // said next would put that stream out of phase instead. The resampler's
    // phase and held sample belong to that utterance for the same reason.
    this.pendingByte = null
    this.resampler?.reset()
  }
  private fail(message: string) {
    if (this.stopped) return
    this.stop()
    this.onState("error")
    this.onError(message)
  }
  stop() {
    this.stopped = true
    this.clearPlayback()
    clearInterval(this.monitor)
    this.stream?.getTracks().forEach((track) => track.stop())
    this.capture?.disconnect()
    if (this.audio?.state !== "closed") void this.audio?.close()
    if (this.input?.state !== "closed") void this.input?.close()
    this.socket?.close()
    this.onState("idle", 0)
  }
  get elapsedSeconds() {
    return Math.floor((Date.now() - this.started) / 1000)
  }
  /**
   * How often the stream arrived too late to be played without a gap.
   *
   * Reported rather than inferred, because the artefact this counts is one a
   * listener describes and a developer cannot reproduce: it depends on their
   * connection, not on the code. A session that ends with zero here did not
   * buzz; one that ends with hundreds is still doing it, and the lead needs to
   * be longer rather than the cause re-guessed.
   */
  get underrunCount() {
    return this.underruns
  }
}
