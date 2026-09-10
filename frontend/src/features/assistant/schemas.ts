import { z } from "zod"

export const artifactKind = z.enum([
  "capabilities",
  "eligibility",
  "calculation",
  "checklist",
  "timeline",
  "scenario",
])
export type ArtifactKind = z.infer<typeof artifactKind>
export type Language = "auto" | "en" | "bn"
export const sourceSchema = z.object({
  id: z.string(),
  label: z.string(),
  quote: z.string(),
  url: z.string().nullable().optional(),
})
export const artifactSchema = z.object({
  id: z.string(),
  version: z.number(),
  kind: artifactKind,
  title: z.string(),
  description: z.string(),
  rows: z.array(
    z.object({
      label: z.string(),
      value: z.number().finite().nullable().optional(),
      baseline: z.number().finite().nullable().optional(),
      detail: z.string(),
      status: z.string().nullable().optional(),
      source_id: z.string().nullable().optional(),
    })
  ),
  formulas: z.array(z.string()),
  assumptions: z.array(z.string()),
  sources: z.array(sourceSchema),
  unit: z.string(),
  context_version: z.string(),
  created_at: z.string(),
})
export type Artifact = z.infer<typeof artifactSchema>
export type Source = z.infer<typeof sourceSchema>
export const messageSchema = z.object({
  id: z.string(),
  request_id: z.string(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  status: z.string(),
  sources: z.array(sourceSchema),
  artifacts: z.array(artifactSchema),
  context_version: z.string(),
  created_at: z.string(),
})
export type ChatMessage = z.infer<typeof messageSchema>
export const conversationSchema = z.object({
  id: z.string(),
  tender_id: z.string().nullable(),
  title: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Conversation = z.infer<typeof conversationSchema>
export const detailSchema = conversationSchema.extend({
  messages: z.array(messageSchema),
})
export const capabilitiesSchema = z.object({
  enabled: z.boolean(),
  voice_enabled: z.boolean(),
  mode: z.enum(["gemini", "demo", "unavailable"]),
  voice_max_seconds: z.number(),
})
export const eventSchema = z.object({
  schema_version: z.literal(1),
  type: z.string(),
  turn_id: z.string(),
  data: z.record(z.string(), z.unknown()),
})
export type AssistantEvent = z.infer<typeof eventSchema>
export type AnalysisRequest = {
  kind: ArtifactKind
  adjustment_percent?: number
}
