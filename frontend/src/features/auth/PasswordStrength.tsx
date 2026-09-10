import {
  Progress,
  ProgressLabel,
  ProgressValue,
} from "@/components/ui/progress"
import { passwordScore, STRENGTH_LABELS } from "@/features/auth/password"

/**
 * Silent until there is a password to judge.
 *
 * It used to render "Too short" against an empty untouched field — telling
 * someone off for a box they had not reached yet, on the account page where the
 * field sits idle most of the time.
 */
export function PasswordStrength({ password }: { password: string }) {
  if (!password) return null
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
