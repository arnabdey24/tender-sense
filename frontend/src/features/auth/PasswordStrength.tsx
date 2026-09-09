import {
  Progress,
  ProgressLabel,
  ProgressValue,
} from "@/components/ui/progress"
import { passwordScore, STRENGTH_LABELS } from "@/features/auth/password"

export function PasswordStrength({ password }: { password: string }) {
  const score = passwordScore(password)

  return (
    <Progress
      value={(score / 4) * 100}
      aria-label="Password strength"
      className="gap-1"
    >
      <ProgressLabel className="text-xs font-normal text-muted-foreground">
        Password strength
      </ProgressLabel>
      <ProgressValue className="text-xs" data-testid="password-strength">
        {() => STRENGTH_LABELS[score]}
      </ProgressValue>
    </Progress>
  )
}
