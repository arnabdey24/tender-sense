import { useMutation } from "@tanstack/react-query"

import { toast } from "@/components/ui/toast"
import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import type { ApiError } from "@/lib/api/errors"

/** Re-send the verification email for an address. */
export function useResendVerification() {
  return useMutation<{ message: string }, ApiError, string>({
    mutationFn: (email) =>
      unwrap(
        api.POST("/api/v1/auth/resend-verification", { body: { email } })
      ),
    onSuccess: (data) =>
      toast.add({
        type: "success",
        title: "Verification email sent",
        description: data.message,
      }),
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not send the email",
        description: error.message,
      }),
  })
}
