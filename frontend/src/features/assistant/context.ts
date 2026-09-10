import { createContext, useContext } from "react"

export const AssistantContext = createContext<{
  openTender: (id: string) => void
} | null>(null)
export function useAssistant() {
  return useContext(AssistantContext)
}
