import { z } from "zod"
import { apiUrl } from "@/lib/api/base"
import { useAuthStore } from "@/lib/auth/store"
import { refreshOnce } from "@/lib/auth/refresh"
import {
  capabilitiesSchema,
  conversationSchema,
  detailSchema,
  eventSchema,
  type AssistantEvent,
} from "./schemas"

const root = "/api/v1/assistant"

export async function assistantFetch(path: string, init: RequestInit = {}) {
  const request = () =>
    fetch(apiUrl(root + path), {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${useAuthStore.getState().accessToken ?? ""}`,
        ...init.headers,
      },
    })
  let response = await request()
  if (response.status === 401 && (await refreshOnce()))
    response = await request()
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string }
    } | null
    throw new Error(
      body?.error?.message ?? "The assistant is unavailable. Please try again."
    )
  }
  return response
}

export const getCapabilities = async () =>
  capabilitiesSchema.parse(await (await assistantFetch("/capabilities")).json())
export const getConversations = async (tenderId?: string) =>
  z
    .array(conversationSchema)
    .parse(
      await (
        await assistantFetch(
          `/conversations${tenderId ? `?tender_id=${encodeURIComponent(tenderId)}` : ""}`
        )
      ).json()
    )
export const getConversation = async (id: string) =>
  detailSchema.parse(
    await (await assistantFetch(`/conversations/${id}`)).json()
  )
/** `null` opens a workspace conversation: the shortlist rather than one notice. */
export const createConversation = async (id: string | null) =>
  conversationSchema.parse(
    await (
      await assistantFetch("/conversations", {
        method: "POST",
        body: JSON.stringify({ tender_id: id }),
      })
    ).json()
  )
export const deleteConversation = async (id: string) =>
  assistantFetch(`/conversations/${id}`, { method: "DELETE" })

/** Fetch-based SSE preserves bearer auth and handles split UTF-8/frame boundaries. */
export async function consumeEvents(
  response: Response,
  onEvent: (event: AssistantEvent) => void
) {
  if (!response.body)
    throw new Error("Streaming is unavailable in this browser.")
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let complete = false
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n")
      let end: number
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, end)
        buffer = buffer.slice(end + 2)
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n")
        if (!data) continue
        const event = eventSchema.parse(JSON.parse(data))
        onEvent(event)
        if (event.type === "complete" || event.type === "error") complete = true
      }
      if (done) break
    }
    if (!complete)
      throw new Error(
        "Connection interrupted. Reopen this conversation to restore the saved response."
      )
  } finally {
    reader.releaseLock()
  }
}
