// Capture mono PCM16 at 16 kHz in 20 ms frames. No microphone audio is stored.
class AssistantCapture extends AudioWorkletProcessor {
  constructor() {
    super()
    this.samples = []
    this.position = 0
    this.frame = []
  }
  process(inputs) {
    const channel = inputs[0]?.[0]
    if (!channel) return true
    this.samples.push(...channel)
    const step = sampleRate / 16000
    while (this.position + 1 < this.samples.length) {
      const i = Math.floor(this.position)
      const t = this.position - i
      const sample = this.samples[i] * (1 - t) + this.samples[i + 1] * t
      this.frame.push(Math.max(-1, Math.min(1, sample)))
      this.position += step
      if (this.frame.length === 320) {
        const pcm = new Int16Array(320)
        let energy = 0
        for (let j = 0; j < 320; j++) {
          pcm[j] = this.frame[j] * 32767
          energy += this.frame[j] ** 2
        }
        this.port.postMessage(
          { audio: pcm.buffer, level: Math.sqrt(energy / 320) },
          [pcm.buffer]
        )
        this.frame = []
      }
    }
    const consumed = Math.floor(this.position)
    this.samples.splice(0, consumed)
    this.position -= consumed
    return true
  }
}
registerProcessor("assistant-capture", AssistantCapture)
