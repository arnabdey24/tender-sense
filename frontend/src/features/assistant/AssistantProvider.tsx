import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { useQuery } from "@tanstack/react-query"
import {
  ArrowUpIcon,
  ArrowUpRightIcon,
  AudioLinesIcon,
  ChartColumnIcon,
  CheckCheckIcon,
  ChevronLeftIcon,
  CopyIcon,
  FileTextIcon,
  HistoryIcon,
  Maximize2Icon,
  MessageCircleIcon,
  Minimize2Icon,
  MinusIcon,
  PlusIcon,
  SearchIcon,
  SparklesIcon,
  SquareIcon,
  Trash2Icon,
  XIcon,
} from "lucide-react"
import { LogoTile } from "@/components/brand/Logo"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group"
import {
  Message,
  MessageContent,
  MessageHeader,
  MessageFooter,
} from "@/components/ui/message"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import {
  MessageScrollerProvider,
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
} from "@/components/ui/message-scroller"
import {
  ResizablePanel,
  ResizablePanelGroup,
  ResizableHandle,
} from "@/components/ui/resizable"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Spinner } from "@/components/ui/spinner"
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Marker, MarkerContent } from "@/components/ui/marker"
import { useAuthStore } from "@/lib/auth/store"
import { qk } from "@/lib/api/query-keys"
import { useTender, useTenders } from "@/features/tenders/api"
import { useMatch } from "@/features/matches/api"
import { useIsMobile } from "@/hooks/use-mobile"
import { cn } from "@/lib/utils"
import { AssistantContext } from "./context"
import {
  assistantFetch,
  consumeEvents,
  createConversation,
  deleteConversation,
  getCapabilities,
  getConversation,
  getConversations,
} from "./api"
import { applyEvent } from "./messages"
import {
  artifactSchema,
  type AnalysisRequest,
  type Artifact,
  type AssistantEvent,
  type ChatMessage,
  type Conversation,
  type Language,
} from "./schemas"
import { RichText } from "./RichText"
import { VoiceControls, VoiceOrb } from "./VoiceControls"
import type { VoiceSession, VoiceState } from "./voice"

const ArtifactView = lazy(() => import("./ArtifactView"))
const STARTERS: {
  label: string
  text: string
  kind?: AnalysisRequest["kind"]
  icon: typeof SparklesIcon
}[] = [
  {
    label: "Explain the recommendation",
    text: "Explain why this tender received its recommendation, including the evidence.",
    icon: SparklesIcon,
  },
  {
    label: "Visualize our capability fit",
    text: "Show our capability match as a chart and explain it.",
    kind: "capabilities",
    icon: ChartColumnIcon,
  },
  {
    label: "Check the eligibility logic",
    text: "Show the eligibility logic and the requirements that need checking.",
    kind: "eligibility",
    icon: CheckCheckIcon,
  },
  {
    label: "Create a preparation checklist",
    text: "Create a draft bid preparation checklist.",
    kind: "checklist",
    icon: FileTextIcon,
  },
]

export function AssistantProvider({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const org = useAuthStore((s) => s.activeOrgId)
  return (
    <AssistantSession
      key={`${org}:${user?.id}`}
      active={!!org && !!user}
      org={org}
      userId={user?.id}
    >
      {children}
    </AssistantSession>
  )
}

function TenderStrip({
  id,
  onChange,
  disabled,
}: {
  id: string
  onChange: () => void
  disabled: boolean
}) {
  const tender = useTender(id)
  const match = useMatch(id)
  return (
    <div className="flex items-center gap-3 border-b bg-muted/35 px-4 py-3">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-background">
        <FileTextIcon className="size-4 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium">
          {tender.data?.title ?? "Loading tender…"}
        </p>
        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
          {tender.data?.external_id ?? "Selected tender"}
          {match.data
            ? ` · Grade ${match.data.grade} · ${match.data.recommendation.toUpperCase()}`
            : " · Not yet assessed"}
        </p>
      </div>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Choose a different tender"
        onClick={onChange}
        disabled={disabled}
      >
        <SearchIcon />
      </Button>
    </div>
  )
}

function TenderPicker({ onSelect }: { onSelect: (id: string) => void }) {
  const [search, setSearch] = useState("")
  const tenders = useTenders({ q: search, page_size: 8, open_only: true })
  return (
    <div className="flex flex-col gap-4 p-5">
      <div>
        <h3 className="font-medium">Choose a tender to explore</h3>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Your assistant will use its notice, your company profile, and the
          recorded assessment.
        </p>
      </div>
      <Input
        aria-label="Search tenders for assistant"
        placeholder="Search tenders…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {tenders.isPending ? (
        <Spinner />
      ) : tenders.error ? (
        <p role="alert" className="text-sm text-destructive">
          Could not load tenders. Please try again.
        </p>
      ) : tenders.data?.items?.length ? (
        <div className="flex flex-col gap-2">
          {tenders.data.items.map((t) => (
            <Button
              key={t.id}
              variant="outline"
              className="h-auto justify-start gap-3 py-3 text-left whitespace-normal"
              onClick={() => onSelect(t.id)}
            >
              <FileTextIcon data-icon="inline-start" />
              <span className="line-clamp-2">{t.title}</span>
            </Button>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          No tenders match this search.
        </p>
      )}
    </div>
  )
}

function AssistantSession({
  children,
  active,
  org,
  userId,
}: {
  children: ReactNode
  active: boolean
  org: string | null
  userId?: string
}) {
  const capabilities = useQuery({
    queryKey: qk.assistant.capabilities(org, userId),
    queryFn: getCapabilities,
    enabled: active,
    staleTime: 60_000,
    retry: false,
  })
  const mobile = useIsMobile()
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<"compact" | "expanded" | "workspace">(
    "compact"
  )
  const [mobileTab, setMobileTab] = useState("conversation")
  const [selected, setSelected] = useState<string | null>(null)
  const [picking, setPicking] = useState(false)
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [artifact, setArtifact] = useState<Artifact | null>(null)
  const [draft, setDraft] = useState("")
  const [language, setLanguage] = useState<Language>("auto")
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<Conversation[] | null>(null)
  const [voiceState, setVoiceState] = useState<VoiceState>("idle")
  const [level, setLevel] = useState(0)
  const [muted, setMuted] = useState(false)
  const [speakerMuted, setSpeakerMuted] = useState(false)
  const [preview, setPreview] = useState(false)
  const [voiceNotice, setVoiceNotice] = useState(false)
  const voice = useRef<VoiceSession | null>(null)
  const controller = useRef<AbortController | null>(null)
  const epoch = useRef(0)
  const working = useRef(false)
  const currentTurn = useRef<string | null>(null)
  const previewTimer = useRef<ReturnType<typeof setInterval> | undefined>(
    undefined
  )
  const live = !["idle", "error"].includes(voiceState)
  const enabled = active && capabilities.data?.enabled !== false

  useEffect(
    () => () => {
      epoch.current++
      controller.current?.abort()
      voice.current?.stop()
      clearInterval(previewTimer.current)
    },
    []
  )

  function endVoice() {
    voice.current?.stop()
    voice.current = null
    clearInterval(previewTimer.current)
    setPreview(false)
    setVoiceState("idle")
    setLevel(0)
    setMuted(false)
    setSpeakerMuted(false)
  }
  function stop() {
    controller.current?.abort()
    currentTurn.current = null
    working.current = false
    setBusy(false)
    setMessages((old) =>
      old.map((m) =>
        m.status === "streaming" ? { ...m, status: "interrupted" } : m
      )
    )
  }
  function showArtifact(value: Artifact) {
    setArtifact(value)
    setMode("workspace")
    setMobileTab("analysis")
  }
  function receive(event: AssistantEvent) {
    setMessages((old) => applyEvent(old, event))
    if (event.type === "artifact")
      showArtifact(artifactSchema.parse(event.data))
    if (event.type === "error")
      setError(String(event.data.message ?? "The assistant could not finish."))
  }
  async function restore(id: string, selectionEpoch: number) {
    const result = await getConversation(id)
    if (epoch.current !== selectionEpoch) return
    setConversation(result)
    setSelected(result.tender_id)
    setMessages(result.messages)
    setArtifact(result.messages.flatMap((m) => m.artifacts).at(-1) ?? null)
  }
  async function selectTender(id: string, fresh = false) {
    setOpen(true)
    setPicking(false)
    setHistory(null)
    if (id === selected && !fresh) return
    stop()
    endVoice()
    const selectionEpoch = ++epoch.current
    setSelected(id)
    setConversation(null)
    setMessages([])
    setArtifact(null)
    setError(null)
    setLoading(true)
    try {
      const recent = fresh ? [] : await getConversations(id)
      if (recent[0]) await restore(recent[0].id, selectionEpoch)
    } catch (cause) {
      if (epoch.current === selectionEpoch)
        setError(
          cause instanceof Error
            ? cause.message
            : "Could not load the conversation."
        )
    } finally {
      if (epoch.current === selectionEpoch) setLoading(false)
    }
  }
  async function ensureConversation() {
    if (conversation) return conversation
    if (!selected) throw new Error("Choose a tender first.")
    const selectionEpoch = epoch.current
    const value = await createConversation(selected)
    if (selectionEpoch === epoch.current) setConversation(value)
    return value
  }
  async function send(text: string, analysis?: AnalysisRequest) {
    if (!text.trim() || working.current || loading) return
    if (live && voice.current) {
      voice.current.sendText(text)
      setDraft("")
      return
    }
    working.current = true
    setBusy(true)
    setError(null)
    setDraft("")
    setMobileTab("conversation")
    const selectionEpoch = epoch.current
    const abort = new AbortController()
    controller.current = abort
    const turnId = crypto.randomUUID()
    currentTurn.current = turnId
    try {
      const value = await ensureConversation()
      if (epoch.current !== selectionEpoch || abort.signal.aborted) return
      setMessages((old) => [
        ...old,
        {
          id: `${turnId}:user`,
          request_id: turnId,
          role: "user",
          content: text,
          status: "complete",
          artifacts: [],
          sources: [],
          context_version: "",
          created_at: new Date().toISOString(),
        },
      ])
      const response = await assistantFetch(
        `/conversations/${value.id}/turns`,
        {
          method: "POST",
          signal: abort.signal,
          body: JSON.stringify({
            request_id: turnId,
            text,
            language,
            artifact: analysis,
            active_artifact: artifact?.kind,
          }),
        }
      )
      await consumeEvents(response, (event) => {
        if (epoch.current === selectionEpoch && currentTurn.current === turnId)
          receive(event)
      })
    } catch (cause) {
      if (epoch.current === selectionEpoch && !abort.signal.aborted) {
        setError(
          cause instanceof Error
            ? cause.message
            : "Could not send your message."
        )
        setMessages((old) =>
          old.map((m) =>
            m.request_id === turnId && m.role === "assistant"
              ? { ...m, status: "error" }
              : m
          )
        )
      }
    } finally {
      if (currentTurn.current === turnId) {
        currentTurn.current = null
        working.current = false
        setBusy(false)
      }
    }
  }
  function analyze(request: AnalysisRequest) {
    void send(
      `Show the ${request.kind} analysis${request.kind === "scenario" ? ` with a hypothetical company turnover change of ${request.adjustment_percent ?? 0}%` : ""}.`,
      request
    )
  }
  async function startVoice() {
    const selectionEpoch = epoch.current
    setVoiceNotice(false)
    setError(null)
    if (capabilities.data?.mode === "demo") {
      setPreview(true)
      setVoiceState("listening")
      let step = 0
      previewTimer.current = setInterval(() => {
        step++
        setVoiceState(
          step % 3 === 0
            ? "listening"
            : step % 3 === 1
              ? "processing"
              : "speaking"
        )
        setLevel(step % 3 === 2 ? 0.7 : 0.25)
      }, 2200)
      return
    }
    setLoading(true)
    try {
      const value = await ensureConversation()
      const { VoiceSession } = await import("./voice")
      if (selectionEpoch !== epoch.current) return
      voice.current = new VoiceSession(
        (state, amplitude) => {
          setVoiceState(state)
          if (amplitude !== undefined) setLevel(amplitude)
        },
        receive,
        setError
      )
      await voice.current.start(value.id, language)
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not start voice."
      )
    } finally {
      if (selectionEpoch === epoch.current) setLoading(false)
    }
  }
  async function showHistory() {
    setLoading(true)
    setError(null)
    try {
      setHistory(await getConversations(selected ?? undefined))
    } catch (cause) {
      setError(String(cause))
    } finally {
      setLoading(false)
    }
  }
  async function removeConversation() {
    if (!conversation) return
    try {
      await deleteConversation(conversation.id)
      setConversation(null)
      setMessages([])
      setArtifact(null)
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not delete conversation."
      )
    }
  }

  const chat = (
    <div className="flex h-full min-h-0 flex-col">
      {selected && (
        <TenderStrip
          id={selected}
          onChange={() => setPicking(true)}
          disabled={busy || live}
        />
      )}
      {capabilities.data?.mode === "demo" && (
        <Marker className="px-4 py-2">
          <MarkerContent>Demo responses · no model calls</MarkerContent>
        </Marker>
      )}
      {picking || !selected ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <TenderPicker onSelect={(id) => void selectTender(id)} />
        </div>
      ) : history ? (
        <div className="flex-1 overflow-y-auto p-4">
          <Button variant="ghost" size="sm" onClick={() => setHistory(null)}>
            <ChevronLeftIcon data-icon="inline-start" />
            Back to conversation
          </Button>
          <div className="mt-3 flex flex-col gap-2">
            {history.length ? (
              history.map((item) => (
                <Button
                  key={item.id}
                  variant="outline"
                  className="h-auto justify-start py-3 text-left whitespace-normal"
                  onClick={() => {
                    const token = ++epoch.current
                    setLoading(true)
                    void restore(item.id, token)
                      .then(() => setHistory(null))
                      .catch((cause) => setError(String(cause)))
                      .finally(() => setLoading(false))
                  }}
                >
                  {item.title}
                  <span className="ml-auto text-xs text-muted-foreground">
                    {new Date(item.created_at).toLocaleDateString()}
                  </span>
                </Button>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">
                No saved conversations yet.
              </p>
            )}
          </div>
        </div>
      ) : (
        <MessageScrollerProvider autoScroll>
          <MessageScroller className="flex-1">
            <MessageScrollerViewport>
              <MessageScrollerContent className="p-5">
                {messages.length === 0 && (
                  <MessageScrollerItem messageId="welcome">
                    <div className="flex flex-col gap-6 pt-5 pb-3">
                      <div className="flex flex-col items-start gap-4">
                        <VoiceOrb />
                        <div>
                          <h2 className="text-2xl leading-tight font-medium tracking-[-0.02em]">
                            Let’s talk it through.
                          </h2>
                          <p className="mt-3 text-pretty text-sm leading-relaxed text-muted-foreground">
                            Explore the fit, follow the evidence, and turn a
                            question into a clearer next step.
                          </p>
                          <p
                            className="mt-2 text-xs text-muted-foreground"
                            lang="bn"
                          >
                            বাংলা বা English—যেভাবে স্বচ্ছন্দ।
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-col gap-2">
                        {STARTERS.map((item) => (
                          <Button
                            key={item.label}
                            variant="outline"
                            className="h-auto justify-start gap-3 py-3 text-left whitespace-normal"
                            disabled={loading || busy}
                            onClick={() =>
                              void send(
                                item.text,
                                item.kind ? { kind: item.kind } : undefined
                              )
                            }
                          >
                            <item.icon data-icon="inline-start" />
                            <span className="flex-1 text-xs">{item.label}</span>
                            <ArrowUpRightIcon data-icon="inline-end" />
                          </Button>
                        ))}
                      </div>
                    </div>
                  </MessageScrollerItem>
                )}
                {messages.map((message) => (
                  <MessageScrollerItem
                    key={message.id}
                    messageId={message.id}
                    scrollAnchor={message.role === "user"}
                  >
                    <Message align={message.role === "user" ? "end" : "start"}>
                      <MessageContent>
                        <MessageHeader>
                          {message.role === "user" ? "You" : "TenderSense"}
                        </MessageHeader>
                        <Bubble
                          variant={
                            message.role === "user" ? "secondary" : "ghost"
                          }
                          align={message.role === "user" ? "end" : "start"}
                        >
                          <BubbleContent>
                            {message.content ? (
                              <RichText
                                text={message.content}
                                sources={message.sources}
                              />
                            ) : (
                              <div className="text-sm leading-relaxed">
                                {message.status === "streaming"
                                  ? "Checking the evidence…"
                                  : "Response interrupted"}
                              </div>
                            )}
                          </BubbleContent>
                        </Bubble>
                        {message.artifacts.map((value, i) => (
                          <Button
                            key={`${value.id}:${i}`}
                            variant="outline"
                            className="h-auto justify-between gap-3 py-3 text-left whitespace-normal"
                            onClick={() => showArtifact(value)}
                          >
                            <ChartColumnIcon data-icon="inline-start" />
                            <span className="flex-1 text-xs">
                              {value.title}
                            </span>
                            <ArrowUpRightIcon data-icon="inline-end" />
                          </Button>
                        ))}
                        {message.sources.length > 0 && (
                          <details className="text-xs">
                            <summary className="cursor-pointer text-muted-foreground">
                              {message.sources.length} evidence sources
                            </summary>
                            <div className="mt-2 flex flex-col gap-3">
                              {message.sources.map((source) => (
                                <blockquote
                                  key={source.id}
                                  className="border-l-2 pl-3"
                                >
                                  <strong className="font-medium">
                                    {source.label}
                                  </strong>
                                  <p className="mt-1 whitespace-pre-wrap text-muted-foreground">
                                    {source.quote}
                                  </p>
                                </blockquote>
                              ))}
                            </div>
                          </details>
                        )}
                        <MessageFooter>
                          {message.status !== "complete" && (
                            <span>
                              {message.status === "streaming"
                                ? "Responding…"
                                : "Incomplete response"}
                            </span>
                          )}
                          {message.content && (
                            <Button
                              variant="ghost"
                              size="icon-xs"
                              aria-label="Copy message"
                              onClick={() =>
                                void navigator.clipboard
                                  .writeText(message.content)
                                  .catch(() =>
                                    setError(
                                      "Copy is unavailable in this browser."
                                    )
                                  )
                              }
                            >
                              <CopyIcon />
                            </Button>
                          )}
                        </MessageFooter>
                      </MessageContent>
                    </Message>
                  </MessageScrollerItem>
                ))}
                {busy && (
                  <MessageScrollerItem messageId="progress">
                    <p
                      role="status"
                      className="shimmer text-xs text-muted-foreground"
                    >
                      Checking the tender and its evidence…
                    </p>
                  </MessageScrollerItem>
                )}
              </MessageScrollerContent>
            </MessageScrollerViewport>
            <MessageScrollerButton />
          </MessageScroller>
        </MessageScrollerProvider>
      )}
      <div className="flex shrink-0 flex-col gap-3 border-t bg-background p-4">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {loading && (
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Spinner />
            Loading conversation…
          </p>
        )}
        {live && (
          <VoiceControls
            state={voiceState}
            level={level}
            muted={muted}
            speakerMuted={speakerMuted}
            preview={preview}
            onMute={() => {
              setMuted(!muted)
              voice.current?.setMuted(!muted)
              if (preview) {
                clearInterval(previewTimer.current)
                setVoiceState(!muted ? "muted" : "listening")
              }
            }}
            onSpeakerMute={() => {
              setSpeakerMuted(!speakerMuted)
              voice.current?.setSpeakerMuted(!speakerMuted)
            }}
            onEnd={endVoice}
          />
        )}
        {voiceNotice && (
          <Alert>
            <AlertDescription>
              <p>
                {capabilities.data?.mode === "demo"
                  ? "Preview the voice animation. This demo does not activate your microphone."
                  : "Audio is sent to our AI service for this conversation. Transcripts are saved; microphone recordings are not stored by TenderSense."}
              </p>
              <div className="mt-2 flex gap-2">
                <Button size="sm" onClick={() => void startVoice()}>
                  {capabilities.data?.mode === "demo"
                    ? "Preview animation"
                    : "Start live voice"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setVoiceNotice(false)}
                >
                  Cancel
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void send(draft)
          }}
        >
          <InputGroup>
            <InputGroupTextarea
              aria-label="Message the tender assistant"
              placeholder={
                selected
                  ? "Ask about this tender…"
                  : "Choose a tender to begin…"
              }
              className="min-h-16"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={!selected || picking || loading}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault()
                  void send(draft)
                }
              }}
            />
            <InputGroupAddon align="block-end">
              <Select
                value={language}
                onValueChange={(value) => {
                  if (value) setLanguage(value as Language)
                }}
                disabled={live}
              >
                <SelectTrigger
                  size="sm"
                  className="h-7 w-24"
                  aria-label="Conversation language"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="auto">Auto</SelectItem>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="bn">বাংলা</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              <div className="ml-auto flex items-center gap-1">
                <InputGroupButton
                  size="icon-sm"
                  aria-label="Start live voice"
                  title={
                    capabilities.data?.voice_enabled ||
                    capabilities.data?.mode === "demo"
                      ? "Start live voice"
                      : "Live voice needs server configuration"
                  }
                  disabled={
                    !selected ||
                    busy ||
                    live ||
                    loading ||
                    (!capabilities.data?.voice_enabled &&
                      capabilities.data?.mode !== "demo")
                  }
                  onClick={() => setVoiceNotice((value) => !value)}
                >
                  <AudioLinesIcon />
                </InputGroupButton>
                {busy ? (
                  <InputGroupButton
                    size="icon-sm"
                    aria-label="Stop response"
                    onClick={stop}
                  >
                    <SquareIcon />
                  </InputGroupButton>
                ) : (
                  <InputGroupButton
                    size="icon-sm"
                    variant="default"
                    type="submit"
                    aria-label="Send message"
                    disabled={!draft.trim() || !selected || loading || picking}
                  >
                    <ArrowUpIcon />
                  </InputGroupButton>
                )}
              </div>
            </InputGroupAddon>
          </InputGroup>
        </form>
        <p className="text-center text-[11px] text-muted-foreground">
          Grounded in your tender. Verify important details against the notice.
        </p>
      </div>
    </div>
  )

  const analysis = (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center">
          <Spinner />
        </div>
      }
    >
      <ArtifactView
        artifact={artifact}
        onAnalyze={analyze}
        busy={busy || loading}
      />
    </Suspense>
  )
  return (
    <AssistantContext.Provider
      value={enabled ? { openTender: (id) => void selectTender(id) } : null}
    >
      {children}
      {enabled && (
        <>
          {!open && (
            <div className="assistant-launcher">
              {/* A labelled pill covers the content beneath it on a phone, so
                  below `sm` the launcher is the icon alone. */}
              <Button
                size="lg"
                aria-label={
                  live ? "Return to live conversation" : "Ask TenderSense"
                }
                className="relative size-12 rounded-full p-0 shadow-lg sm:h-12 sm:w-auto sm:px-5"
                onClick={() => setOpen(true)}
              >
                <MessageCircleIcon data-icon="inline-start" />
                <span className="hidden sm:inline">
                  {live ? "Return to live conversation" : "Ask TenderSense"}
                </span>
                {live && (
                  <span className="absolute top-1 right-1 size-2 rounded-full bg-success sm:static" />
                )}
              </Button>
              {live && (
                <Button variant="destructive" size="sm" onClick={endVoice}>
                  End voice
                </Button>
              )}
            </div>
          )}
          <Dialog
            open={open}
            modal={mode === "workspace"}
            onOpenChange={(value) => {
              setOpen(value)
              if (!value) endVoice()
            }}
          >
            <DialogContent
              showCloseButton={false}
              showOverlay={mode === "workspace"}
              className={cn(
                "assistant-panel flex flex-col gap-0 overflow-hidden p-0",
                mode === "workspace"
                  ? "assistant-panel-workspace"
                  : mode === "expanded"
                    ? "assistant-panel-expanded"
                    : "assistant-panel-compact"
              )}
            >
              <div className="flex shrink-0 items-center gap-3 border-b px-4 py-3">
                {/*
                  The mark, not a generic sparkle: on a full-screen phone sheet
                  this row is the only chrome the panel has, so it has to say
                  whose assistant this is.
                */}
                <LogoTile size={32} />
                <div className="min-w-0 flex-1">
                  {/*
                    "TenderSense assistant" needs two lines beside five action
                    buttons at 420px, and truncates to "TenderSense as…" on a
                    phone. The mark to the left carries the product name, so the
                    visible title stays short and the description below spells it
                    out for screen readers.
                  */}
                  <DialogTitle className="truncate text-sm font-medium">
                    Assistant
                  </DialogTitle>
                  {/*
                    The tagline that used to sit here ("a clearer path from
                    notice to decision") told the reader nothing and wrapped to
                    two lines, so the header ate 190px of a phone screen. The
                    panel already states its grounding twice below — the mode
                    marker and the composer footnote — so this stays for screen
                    readers only.
                  */}
                  <DialogDescription className="sr-only">
                    TenderSense assistant. Ask about the selected tender;
                    answers are grounded in its notice, your company profile,
                    and the recorded assessment.
                  </DialogDescription>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Conversation history"
                  disabled={busy || live || loading}
                  onClick={() => void showHistory()}
                >
                  <HistoryIcon />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="New conversation"
                  disabled={!selected || busy || live || loading}
                  onClick={() => selected && void selectTender(selected, true)}
                >
                  <PlusIcon />
                </Button>
                {/*
                  Expand and minimize describe nothing on a phone: the sheet is
                  already the whole screen, and closing it is what the X does.
                  Five icon-only controls in a 390px row is also more than the
                  header can carry legibly.
                */}
                {!mobile && (
                  <>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={
                        mode === "compact" ? "Expand chat" : "Compact chat"
                      }
                      onClick={() =>
                        setMode(mode === "compact" ? "expanded" : "compact")
                      }
                    >
                      {mode === "compact" ? (
                        <Maximize2Icon />
                      ) : (
                        <Minimize2Icon />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Minimize assistant"
                      onClick={() => setOpen(false)}
                    >
                      <MinusIcon />
                    </Button>
                  </>
                )}
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Close assistant"
                  onClick={() => {
                    setOpen(false)
                    endVoice()
                  }}
                >
                  <XIcon />
                </Button>
              </div>
              {mode === "workspace" && mobile && (
                <ToggleGroup
                  value={[mobileTab]}
                  onValueChange={(value) => value[0] && setMobileTab(value[0])}
                  className="mx-4 my-2"
                  aria-label="Workspace view"
                >
                  <ToggleGroupItem value="conversation">
                    Conversation
                  </ToggleGroupItem>
                  <ToggleGroupItem value="analysis">Analysis</ToggleGroupItem>
                </ToggleGroup>
              )}
              <div className="min-h-0 flex-1">
                {mode === "workspace" ? (
                  mobile ? (
                    mobileTab === "conversation" ? (
                      chat
                    ) : (
                      analysis
                    )
                  ) : (
                    <ResizablePanelGroup orientation="horizontal">
                      <ResizablePanel defaultSize="40%" minSize="320px">
                        {chat}
                      </ResizablePanel>
                      <ResizableHandle withHandle />
                      <ResizablePanel defaultSize="60%" minSize="350px">
                        {analysis}
                      </ResizablePanel>
                    </ResizablePanelGroup>
                  )
                ) : (
                  chat
                )}
              </div>
              <div className="flex shrink-0 items-center justify-between gap-2 border-t bg-muted/25 px-4 py-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!selected}
                  onClick={() => {
                    setMode("workspace")
                    setMobileTab("analysis")
                  }}
                >
                  <ChartColumnIcon data-icon="inline-start" />
                  Analysis workspace
                  <ArrowUpRightIcon data-icon="inline-end" />
                </Button>
                {conversation && (
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    aria-label="Delete this conversation"
                    disabled={busy || live || loading}
                    onClick={() => void removeConversation()}
                  >
                    <Trash2Icon />
                  </Button>
                )}
                <Badge variant="outline">Private</Badge>
              </div>
            </DialogContent>
          </Dialog>
        </>
      )}
    </AssistantContext.Provider>
  )
}
