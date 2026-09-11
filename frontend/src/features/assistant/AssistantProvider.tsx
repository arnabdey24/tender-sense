import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import {
  ArrowUpIcon,
  ArrowUpRightIcon,
  BellIcon,
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
  ListChecksIcon,
  MessageCircleQuestionIcon,
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
import { useAuthStore, useIsSuperuser } from "@/lib/auth/store"
import { qk } from "@/lib/api/query-keys"
import { useTender, useTenders } from "@/features/tenders/api"
import { useMatch } from "@/features/matches/api"
import { useDraggableCorner } from "@/hooks/use-draggable-corner"
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
import { applyEvent, initialScrollPosition } from "./messages"
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

/**
 * The microphone disclosure is shown before the first live session and then
 * remembered, so starting voice afterwards is the one tap it should be. It is
 * a disclosure, not a consent record — the browser still asks for the
 * microphone itself every time it needs to.
 */
/**
 * Why live voice is off, in a sentence the reader can act on.
 *
 * The control used to be greyed with a `title` explaining nothing — a tooltip
 * no touch screen shows, on a button that could not be pressed to ask. Every
 * one of these ends the same way on purpose: whatever is missing, text analysis
 * is not, and that is the thing the reader most needs to know.
 */
const VOICE_UNAVAILABLE: Record<string, string> = {
  assistant_off: "The assistant is switched off for this deployment.",
  voice_off:
    "Live voice is switched off for this deployment. Everything else in the assistant works as usual.",
  no_key:
    "Live voice needs a speech key this deployment does not have. Everything else in the assistant works as usual.",
  provider_not_gemini:
    "This deployment runs the offline model, which has no live voice. Everything else in the assistant works as usual.",
}

/** The setting an operator would change. Shown only to platform staff. */
const VOICE_SETTING: Record<string, string> = {
  assistant_off: "ASSISTANT_ENABLED",
  voice_off: "ASSISTANT_VOICE_ENABLED",
  no_key: "GEMINI_API_KEY",
  provider_not_gemini: "AI_PROVIDER",
}

const VOICE_NOTICE_SEEN = "tendersense.assistant.voiceNoticeSeen"

function voiceNoticeSeen() {
  try {
    return localStorage.getItem(VOICE_NOTICE_SEEN) === "1"
  } catch {
    // Private mode or blocked storage: show the notice, which is the safe way to be wrong.
    return false
  }
}

function rememberVoiceNotice() {
  try {
    localStorage.setItem(VOICE_NOTICE_SEEN, "1")
  } catch {
    /* Nothing to remember it with; the notice simply shows again. */
  }
}

/**
 * A plain-language name for where the user is standing, so "explain this"
 * resolves and the assistant does not offer to open the page already on screen.
 */
function describePage(pathname: string) {
  if (/^\/app\/tenders\/[^/]+$/.test(pathname)) return "a tender's detail page"
  const named: Record<string, string> = {
    "/app/dashboard": "the dashboard",
    "/app/today": "today's shortlist",
    "/app/matches": "the matches list",
    "/app/tenders": "the tender pool",
    "/app/pipeline": "the pipeline",
    "/app/notifications": "notifications",
    "/account": "their account",
  }
  if (named[pathname]) return named[pathname]
  if (pathname.startsWith("/app/settings")) return "settings"
  return undefined
}

/** Pages `open_in_app` may open, mirroring the server's allow-list exactly. */
const PAGE_ROUTES = {
  dashboard: "/app/dashboard",
  today: "/app/today",
  matches: "/app/matches",
  tenders: "/app/tenders",
  pipeline: "/app/pipeline",
  notifications: "/app/notifications",
  settings: "/app/settings",
  "settings/profile": "/app/settings/profile",
  "settings/rules": "/app/settings/rules",
  "settings/members": "/app/settings/members",
  "settings/organization": "/app/settings/organization",
  "settings/notifications": "/app/settings/notifications",
  "settings/sources": "/app/settings/sources",
  account: "/account",
} as const

/**
 * Search params each list route understands. The server validates the values;
 * this decides which of them a given page actually accepts, so asking for a
 * grade on the tender pool drops the grade rather than putting an unknown key
 * in the URL.
 */
const PAGE_FILTERS: Record<string, readonly string[]> = {
  tenders: ["q", "category", "status", "source", "open_only", "sort"],
  matches: ["grade", "eligibility", "recommendation", "sort"],
}

/** Sorts differ per route; an unrecognised one is dropped, not passed through. */
const SORTS: Record<string, readonly string[]> = {
  tenders: ["published_at", "deadline_at", "title", "estimated_value"],
  matches: ["similarity", "deadline_at", "published_at", "created_at"],
}

function filtersFor(page: string, raw: Record<string, unknown>) {
  const allowed = PAGE_FILTERS[page]
  if (!allowed) return {}
  const out: Record<string, unknown> = {}
  for (const key of allowed) {
    const value = raw[key]
    if (value === undefined || value === null || value === "") continue
    if (key === "sort" && !SORTS[page]?.includes(String(value))) continue
    out[key] = value
  }
  return out
}
type Starter = {
  label: string
  text: string
  kind?: AnalysisRequest["kind"]
  icon: typeof ChartColumnIcon
}

const WORKSPACE_STARTERS: Starter[] = [
  {
    label: "What should I look at today?",
    text: "Which of my matches are worth looking at today, and why?",
    icon: ListChecksIcon,
  },
  {
    label: "What is closing soonest?",
    text: "Which of my matches have the nearest deadlines?",
    icon: MessageCircleQuestionIcon,
  },
  {
    label: "Open my strongest match",
    text: "Open the tender with the strongest match for my company.",
    icon: ArrowUpRightIcon,
  },
  {
    label: "Take me to notification settings",
    text: "Take me to my notification settings.",
    icon: BellIcon,
  },
]

const STARTERS: Starter[] = [
  {
    label: "Explain the recommendation",
    text: "Explain why this tender received its recommendation, including the evidence.",
    icon: MessageCircleQuestionIcon,
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
    icon: ListChecksIcon,
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
          Answers use its notice, your company profile and the recorded
          assessment.
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
  const navigate = useNavigate()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const mobile = useIsMobile()
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<"compact" | "expanded" | "workspace">(
    "compact"
  )
  const [mobileTab, setMobileTab] = useState("conversation")
  const [selected, setSelected] = useState<string | null>(null)
  const [picking, setPicking] = useState(false)
  /**
   * Bumped whenever a fresh conversation starts, and used as the welcome
   * orb's key so it remounts and replays its wake.
   *
   * Pressing New conversation on a chat that is already empty is a no-op by
   * definition — there is nothing to clear — and with no visible response it
   * reads as a broken button. Replaying the orb answers the press: yes, this
   * is a new conversation.
   */
  const [chatEpoch, setChatEpoch] = useState(0)
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
  const isSuperuser = useIsSuperuser()

  // Demo mode has no microphone but does have the animation to preview, so it
  // is a working control rather than an unavailable one.
  const voiceReason = capabilities.data?.voice_unavailable_reason ?? null
  const voiceUnavailable =
    !capabilities.data?.voice_enabled && capabilities.data?.mode !== "demo"
  const voice = useRef<VoiceSession | null>(null)
  const controller = useRef<AbortController | null>(null)
  const epoch = useRef(0)
  const working = useRef(false)
  const currentTurn = useRef<string | null>(null)
  const previewTimer = useRef<ReturnType<typeof setInterval> | undefined>(
    undefined
  )
  // Matches the CSS anchor the launcher shipped with, so a reader who never
  // drags it sees no change.
  const launcher = useDraggableCorner({
    storageKey: "assistant-launcher:offset",
    defaultOffset: { right: 24, bottom: 24 },
    size: { width: 56, height: 56 },
  })

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
    if (event.type === "navigate") openTarget(event.data)
    if (event.type === "error")
      setError(String(event.data.message ?? "The assistant could not finish."))
  }
  /**
   * Move the workspace behind the panel. The panel stays where it is and the
   * conversation keeps going — being taken somewhere should not cost you the
   * thread you were in the middle of, and on a phone the sheet shrinks to the
   * compact panel so the page it just opened is actually visible.
   */
  function openTarget(data: Record<string, unknown>) {
    const tenderId = data.tender_id ? String(data.tender_id) : null
    const page = data.page ? String(data.page) : ""
    const route = PAGE_ROUTES[page as keyof typeof PAGE_ROUTES]
    if (!tenderId && !route) return
    if (mobile) setOpen(false)
    else if (mode === "workspace") setMode("expanded")
    if (tenderId) {
      void navigate({ to: "/app/tenders/$tenderId", params: { tenderId } })
      return
    }
    const search = filtersFor(
      page,
      (data.filters as Record<string, unknown>) ?? {}
    )
    void navigate({ to: route, search: search as never })
  }
  async function restore(id: string, selectionEpoch: number) {
    const result = await getConversation(id)
    if (epoch.current !== selectionEpoch) return
    setConversation(result)
    setSelected(result.tender_id)
    setMessages(result.messages)
    setArtifact(result.messages.flatMap((m) => m.artifacts).at(-1) ?? null)
  }
  /**
   * Point the panel at a tender, or at the workspace.
   *
   * `null` is the workspace conversation — about the shortlist rather than one
   * notice — and is the state the panel opens in from the launcher, so this
   * has to accept it. It used to take a bare `string`, which is what made the
   * New conversation button dead on exactly the conversation most people
   * start in.
   */
  async function selectTender(id: string | null, fresh = false) {
    setOpen(true)
    setPicking(false)
    setHistory(null)
    // `fresh` is the whole point of the New conversation button, so it must
    // never be short-circuited by "you are already on this tender".
    if (id === selected && !fresh) return
    stop()
    endVoice()
    const selectionEpoch = ++epoch.current
    setSelected(id)
    setConversation(null)
    setMessages([])
    setChatEpoch((n) => n + 1)
    setArtifact(null)
    setError(null)
    setLoading(true)
    try {
      const recent = fresh ? [] : await getConversations(id ?? undefined)
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
    const selectionEpoch = epoch.current
    // `null` is a workspace conversation — about the shortlist, not one notice.
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
            page: describePage(pathname),
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
    rememberVoiceNotice()
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
          <MarkerContent>Demo mode · sample replies, not your data</MarkerContent>
        </Marker>
      )}
      {picking ? (
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
        /*
          Two separate things put an empty panel at the bottom of its own
          greeting, and fixing only the first left the bug alive on short
          windows.

          `autoScroll` follows new content, and following nothing means sitting
          at the end — so it starts when there is something to follow.

          `defaultScrollPosition` is the one that actually bit: it defaults to
          "end", independent of autoScroll, and it is applied on mount. A tall
          window hides it, because the greeting fits and the end *is* the start;
          under about 520px of viewport the content overflows and the panel
          opens on a half-cut sentence above four suggestion buttons with no
          visible reason for being there. A greeting is read from the top; a
          conversation with history is resumed at its end.
        */
        <MessageScrollerProvider
          autoScroll={messages.length > 0}
          defaultScrollPosition={initialScrollPosition(messages.length)}
        >
          <MessageScroller className="flex-1">
            <MessageScrollerViewport>
              <MessageScrollerContent className="p-5">
                {messages.length === 0 && (
                  <MessageScrollerItem messageId="welcome">
                    <div className="assistant-welcome flex flex-col gap-6 pt-5 pb-3">
                      <div className="flex flex-col items-start gap-4">
                        <VoiceOrb key={chatEpoch} intro />
                        <div>
                          <h2 className="assistant-welcome-title text-2xl leading-tight font-medium tracking-[-0.02em]">
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
                        {(selected ? STARTERS : WORKSPACE_STARTERS).map((item) => (
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
                {voiceUnavailable
                  ? (VOICE_UNAVAILABLE[voiceReason ?? ""] ??
                    "Live voice is not configured for this deployment. Everything else in the assistant works as usual.")
                  : capabilities.data?.mode === "demo"
                    ? "Preview the voice animation. This demo does not activate your microphone."
                    : "Your microphone is sent to the speech service that powers this conversation. Transcripts are saved; recordings are not stored by TenderSense."}
              </p>
              {/*
                The setting, for the one reader who can change it. A member
                being handed an environment variable name would be handed
                somebody else's job.
              */}
              {voiceUnavailable && isSuperuser && voiceReason && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Set <code>{VOICE_SETTING[voiceReason]}</code> on the API and
                  restart it.
                </p>
              )}
              <div className="mt-2 flex gap-2">
                {!voiceUnavailable && (
                  <Button size="sm" onClick={() => void startVoice()}>
                    {capabilities.data?.mode === "demo"
                      ? "Preview animation"
                      : "Start live voice"}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setVoiceNotice(false)}
                >
                  {voiceUnavailable ? "Close" : "Cancel"}
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
                  : "Ask about your shortlist, or where to go…"
              }
              className="min-h-16"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={picking || loading}
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
                  // The addon paints its children in muted-foreground, which is
                  // the same grey a disabled control uses — so an enabled
                  // microphone looked switched off. Ink weight, brand on hover.
                  className="text-foreground hover:text-primary disabled:text-muted-foreground"
                  aria-label={
                    voiceUnavailable
                      ? "Why live voice is unavailable"
                      : "Start live voice"
                  }
                  // Not disabled when voice is off, deliberately. A control
                  // that does nothing and will not say why is the whole
                  // complaint; this one answers the press with the reason, in
                  // the panel rather than in a tooltip no phone will show.
                  disabled={busy || live || loading}
                  onClick={() =>
                    voiceUnavailable || !voiceNoticeSeen()
                      ? setVoiceNotice((value) => !value)
                      : void startVoice()
                  }
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
                    disabled={!draft.trim() || loading || picking}
                  >
                    <ArrowUpIcon />
                  </InputGroupButton>
                )}
              </div>
            </InputGroupAddon>
          </InputGroup>
        </form>
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
            <div
              className="assistant-launcher"
              style={{
                right: launcher.offset.right,
                bottom: launcher.offset.bottom,
              }}
            >
              {/*
                48px sat under the comfortable target size for a control that
                floats over content and is reached one-handed on a phone. 56px,
                still icon-only — the label is on the button's accessible name,
                not printed beside it.

                It is also draggable, because a fixed corner button always
                covers *something*: the last row of a table, the pagination, a
                form's submit. Rather than guess which corner is safe, the
                reader moves it and it stays moved. A press that does not
                travel is still a click, so activation is unaffected, and
                keyboard users are untouched — the drag is pointer-only.
              */}
              <Button
                size="lg"
                aria-label={
                  live ? "Return to live conversation" : "Ask TenderSense"
                }
                title="Ask TenderSense — drag to move"
                className={cn(
                  "group/launcher relative size-14 touch-none rounded-full p-0 shadow-lg",
                  // It should look pressable before it is pressed: the button
                  // lifts under a pointer and gives under one.
                  "transition-[transform,box-shadow] duration-[var(--motion-base)] ease-(--motion-ease-out)",
                  "hover:scale-105 hover:shadow-xl active:scale-95 active:duration-[var(--motion-fast)]",
                  launcher.dragging
                    ? "scale-105 cursor-grabbing shadow-xl"
                    : "cursor-grab"
                )}
                {...launcher.handlers}
                onClick={() => {
                  // Swallow the click that ends a drag; open on a real press.
                  if (launcher.consumeDrag()) return
                  setOpen(true)
                }}
                onDoubleClick={launcher.reset}
              >
                <MessageCircleIcon className="size-6! transition-transform duration-[var(--motion-base)] ease-(--motion-ease-out) group-hover/launcher:-rotate-6" />
                {live && (
                  <span className="absolute top-1.5 right-1.5 size-2.5 rounded-full bg-success ring-2 ring-primary" />
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
                // `top-auto left-auto translate-none` are not decoration: the
                // dialog's own base classes centre it with `top-1/2 left-1/2
                // -translate-x-1/2 -translate-y-1/2`, and `index.css` tried to
                // undo that in a rule that sits in the same `@layer utilities`
                // as the utilities themselves. Same layer, same specificity, so
                // source order decides — and the production build emits the
                // utility last while the dev server happened to emit it first.
                // The panel was therefore correct in development and shifted by
                // half its own size on the deployed site: 210px left, 370px up,
                // its header off the top of the window.
                //
                // Naming the conflict in the class list instead means the
                // merger drops the centring classes before they ever reach the
                // DOM, so there is nothing left to win or lose a cascade.
                "assistant-panel top-auto left-auto translate-none",
                "flex flex-col gap-0 overflow-hidden p-0",
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
                  disabled={busy || live || loading}
                  // No truthiness guard on `selected`: null is the workspace
                  // conversation, not "nothing selected", and guarding on it
                  // meant this button did nothing at all in the state the
                  // panel opens in.
                  onClick={() => void selectTender(selected, true)}
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
                  disabled={false}
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
