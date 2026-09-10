import type { CSSProperties } from "react"
import {
  MicIcon,
  MicOffIcon,
  PhoneOffIcon,
  Volume2Icon,
  VolumeXIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import type { VoiceState } from "./voice"

const labels: Record<VoiceState, string> = {
  idle: "Ready to talk",
  permission: "Waiting for microphone permission",
  connecting: "Connecting…",
  listening: "Listening to you",
  processing: "Working on your question…",
  speaking: "Speaking",
  muted: "Microphone muted",
  error: "Voice disconnected",
}

export function VoiceOrb({
  state = "idle",
  level = 0,
  small = false,
  intro = false,
  live = false,
}: {
  state?: VoiceState
  level?: number
  small?: boolean
  /**
   * Play the one-shot wake as the orb appears. Finite by design: it reports
   * that the assistant has arrived, then rests.
   */
  intro?: boolean
  /**
   * A voice session is connected. Idle then means "the line is open" rather
   * than "nothing is happening", so the orb keeps breathing to say so.
   */
  live?: boolean
}) {
  return (
    <div
      className="assistant-orb"
      data-state={state}
      data-small={small}
      data-intro={intro || undefined}
      data-live={live || undefined}
      aria-hidden="true"
      style={{ "--voice-level": level } as CSSProperties}
    >
      <div className="assistant-orb-core" />
      <div className="assistant-orb-ring" />
      <div className="assistant-orb-ring assistant-orb-ring-second" />
    </div>
  )
}

export function VoiceControls({
  state,
  level,
  muted,
  speakerMuted,
  onMute,
  onSpeakerMute,
  onEnd,
  preview,
}: {
  state: VoiceState
  level: number
  muted: boolean
  speakerMuted: boolean
  onMute: () => void
  onSpeakerMute: () => void
  onEnd: () => void
  preview: boolean
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-muted/40 p-3">
      <VoiceOrb small live state={state} level={level} />
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium" role="status">
          {labels[state]}
        </p>
        <p className="text-[11px] text-muted-foreground">
          {preview
            ? "Animation preview · microphone is off"
            : "Live voice · you can interrupt"}
        </p>
      </div>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={muted ? "Unmute microphone" : "Mute microphone"}
        onClick={onMute}
      >
        {muted ? <MicOffIcon /> : <MicIcon />}
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={speakerMuted ? "Unmute speaker" : "Mute speaker"}
        onClick={onSpeakerMute}
      >
        {speakerMuted ? <VolumeXIcon /> : <Volume2Icon />}
      </Button>
      <Button
        variant="destructive"
        size="icon-sm"
        aria-label="End voice"
        onClick={onEnd}
      >
        <PhoneOffIcon />
      </Button>
    </div>
  )
}
