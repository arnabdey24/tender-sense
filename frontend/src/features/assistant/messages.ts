import {
  artifactSchema,
  sourceSchema,
  type AssistantEvent,
  type ChatMessage,
} from "./schemas"

export function applyEvent(
  messages: ChatMessage[],
  event: AssistantEvent
): ChatMessage[] {
  if (!event.turn_id) return messages
  const role =
    event.type === "transcript" && event.data.role === "user"
      ? "user"
      : "assistant"
  let found = messages.find(
    (m) => m.request_id === event.turn_id && m.role === role
  )
  if (!found)
    found = {
      id: `${event.turn_id}:${role}`,
      request_id: event.turn_id,
      role,
      content: "",
      status: "streaming",
      artifacts: [],
      sources: [],
      context_version: "",
      created_at: new Date().toISOString(),
    }
  let next = { ...found }
  if (event.type === "start")
    next = {
      ...next,
      id: String(event.data.message_id ?? found.id),
      sources: sourceSchema.array().parse(event.data.sources ?? []),
      context_version: String(event.data.context_version ?? ""),
    }
  if (event.type === "text" || event.type === "transcript")
    next.content += String(event.data.text ?? "")
  if (event.type === "artifact") {
    const artifact = artifactSchema.parse(event.data)
    next.artifacts = [
      ...next.artifacts.filter(
        (a) => a.id !== artifact.id || a.version !== artifact.version
      ),
      artifact,
    ]
  }
  if (event.type === "complete") next.status = "complete"
  if (event.type === "interrupted" || event.type === "error")
    next.status = event.type
  const result = messages.some(
    (m) => m.request_id === event.turn_id && m.role === role
  )
    ? messages.map((m) =>
        m.request_id === event.turn_id && m.role === role ? next : m
      )
    : [...messages, next]
  return event.type === "complete"
    ? result.map((m) =>
        m.request_id === event.turn_id ? { ...m, status: "complete" } : m
      )
    : result
}
