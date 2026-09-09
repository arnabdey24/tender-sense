import { MailIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { useResendVerification } from "@/features/auth/mutations"

export function ResendVerificationButton({
  email,
  variant = "outline",
  size = "sm",
  label = "Resend verification email",
}: {
  email: string
  variant?: React.ComponentProps<typeof Button>["variant"]
  size?: React.ComponentProps<typeof Button>["size"]
  label?: string
}) {
  const resend = useResendVerification()

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      disabled={!email || resend.isPending}
      onClick={() => resend.mutate(email)}
    >
      {resend.isPending ? (
        <Spinner data-icon="inline-start" />
      ) : (
        <MailIcon data-icon="inline-start" />
      )}
      {label}
    </Button>
  )
}
