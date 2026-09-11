import { apiUrl } from "@/lib/api/base"
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

export class VoiceSession {
  private socket?: WebSocket
  private stream?: MediaStream
  private audio?: AudioContext
  /** Half a sample, waiting for the byte that completes it. */
  private pendingByte: number | null = null
  private capture?: AudioWorkletNode
  private sources = new Set<AudioBufferSourceNode>()
  private nextPlayback = 0
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
      this.audio = new AudioContext()
      await this.audio.resume()
      await this.audio.audioWorklet.addModule("/assistant-audio.js")
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
    if (!this.audio || !this.stream || this.stopped) return
    const input = this.audio.createMediaStreamSource(this.stream)
    this.capture = new AudioWorkletNode(this.audio, "assistant-capture")
    const silent = this.audio.createGain()
    silent.gain.value = 0
    input.connect(this.capture).connect(silent).connect(this.audio.destination)
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
        this.audio.currentTime >= this.nextPlayback
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
    const buffer = this.audio.createBuffer(1, bytes.length / 2, 24000)
    const channel = buffer.getChannelData(0)
    let energy = 0
    for (let i = 0; i < channel.length; i++) {
      channel[i] = view.getInt16(i * 2, true) / 32768
      energy += channel[i] ** 2
    }
    if (this.nextPlayback - this.audio.currentTime > 30) {
      this.fail("Audio playback fell behind. Please restart voice.")
      return
    }
    const source = this.audio.createBufferSource()
    source.buffer = buffer
    source.connect(this.outputGain)
    this.sources.add(source)
    source.onended = () => this.sources.delete(source)
    this.nextPlayback = Math.max(this.audio.currentTime, this.nextPlayback)
    source.start(this.nextPlayback)
    this.nextPlayback += buffer.duration
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
    this.nextPlayback = 0
    this.speaking = false
    // An interruption discards the rest of that utterance, so a half sample
    // held from it has nothing to complete it — carrying it into whatever is
    // said next would put that stream out of phase instead.
    this.pendingByte = null
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
    this.socket?.close()
    this.onState("idle", 0)
  }
  get elapsedSeconds() {
    return Math.floor((Date.now() - this.started) / 1000)
  }
}
