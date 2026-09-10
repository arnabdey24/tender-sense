import { describe, expect, it } from "vitest"
import { applyEvent } from "./messages"
import { consumeEvents } from "./api"
import type { AssistantEvent } from "./schemas"

const event = (type: string, data = {}): AssistantEvent => ({ schema_version: 1, type, data, turn_id: "turn-1" })

describe("assistant conversation events", () => {
  it("keeps voice input and output in the same turn without mixing speakers", () => {
    let messages = applyEvent([], event("transcript", { role: "user", text: "বাংলায় " }))
    messages = applyEvent(messages, event("transcript", { role: "user", text: "বলুন" }))
    messages = applyEvent(messages, event("transcript", { role: "assistant", text: "এই দরপত্র…" }))
    messages = applyEvent(messages, event("complete"))
    expect(messages.map(m => [m.role, m.content, m.status])).toEqual([["user", "বাংলায় বলুন", "complete"], ["assistant", "এই দরপত্র…", "complete"]])
  })

  it("preserves the received text when interrupted", () => {
    const messages = applyEvent(applyEvent([], event("text", { text: "The requirement" })), event("interrupted"))
    expect(messages[0]).toMatchObject({ content: "The requirement", status: "interrupted" })
  })

  it("decodes split Bengali UTF-8 and SSE frame boundaries", async () => {
    const bytes = new TextEncoder().encode(`data: ${JSON.stringify(event("text", { text: "বাংলা" }))}\n\ndata: ${JSON.stringify(event("complete"))}\n\n`)
    const stream = new ReadableStream({ start(controller) { for (const byte of bytes) controller.enqueue(Uint8Array.of(byte)); controller.close() } })
    const seen: AssistantEvent[] = []
    await consumeEvents(new Response(stream), e => seen.push(e))
    expect(seen[0].data.text).toBe("বাংলা")
    expect(seen[1].type).toBe("complete")
  })

  it("does not claim success after a truncated connection", async () => {
    await expect(consumeEvents(new Response(`data: ${JSON.stringify(event("text", { text: "Partial" }))}\n\n`), () => {})).rejects.toThrow("interrupted")
  })
})
