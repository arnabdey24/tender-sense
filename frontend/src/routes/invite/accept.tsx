import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { CheckIcon, UserRoundXIcon } from "lucide-react"
import { z } from "zod"

import { AuthCard } from "@/components/layout/AuthCard"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { toast } from "@/components/ui/toast"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import type { ApiError } from "@/lib/api/errors"
import { qk } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/schema"
import { waitForAuth } from "@/lib/auth/bootstrap"
import { refreshSession, signOut } from "@/lib/auth/session"
import { useAuthStore } from "@/lib/auth/store"
import { LoginForm } from "@/routes/_auth/login"
import { RegisterForm } from "@/routes/_auth/register"

const searchSchema = z.object({
  token: z.string().optional(),
})

export const Route = createFileRoute("/invite/accept")({
  validateSearch: searchSchema,
  // Settle the silent refresh first so the panel knows who (if anyone) is here.
  beforeLoad: () => waitForAuth(),
  component: InviteAcceptPage,
})

type Preview = components["schemas"]["InvitationPreview"]

function InviteSummary({ preview }: { preview: Preview }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium">{preview.org_name}</span>
        <Badge variant="secondary">{preview.role}</Badge>
      </div>
      <p className="text-sm text-muted-foreground">
        {preview.inviter_name ? `${preview.inviter_name} invited ` : "Invited "}
        <span className="font-medium text-foreground">{preview.email}</span> to
        join.
      </p>
    </div>
  )
}

export function InviteAcceptPanel({ token }: { token?: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const status = useAuthStore((s) => s.status)
  const user = useAuthStore((s) => s.user)

  const preview = useQuery<Preview, ApiError>({
    queryKey: qk.invitations.preview(token ?? ""),
    enabled: !!token,
    retry: false,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/invitations/{token}", {
          params: { path: { token: token as string } },
        })
      ),
  })

  const accept = useMutation<unknown, ApiError, void>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/invitations/{token}/accept", {
          params: { path: { token: token as string } },
        })
      ),
    onSuccess: async () => {
      // The access token in hand predates the new membership — refresh so the
      // org claim is present before any org-scoped request goes out.
      await refreshSession(queryClient)
      toast.add({
        type: "success",
        title: "Invitation accepted",
        description: `You have joined ${preview.data?.org_name ?? "the organization"}.`,
      })
      await navigate({ to: "/app/dashboard" })
    },
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not accept the invitation",
        description: error.message,
      }),
  })

  const inviteHref = `/invite/accept?token=${encodeURIComponent(token ?? "")}`

  if (!token) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Missing invitation token</AlertTitle>
        <AlertDescription>
          Open the invitation link from your email again.
        </AlertDescription>
      </Alert>
    )
  }

  if (preview.isPending || status === "booting") {
    return (
      <div className="flex justify-center py-6" data-testid="invite-loading">
        <Spinner className="size-6" />
      </div>
    )
  }

  if (preview.isError) {
    return (
      <div className="flex flex-col gap-4">
        <ApiErrorAlert error={preview.error} />
        <Button render={<Link to="/login" />} nativeButton={false}>
          Go to sign in
        </Button>
      </div>
    )
  }

  const invitation = preview.data

  // Signed out: let them sign in or sign up without losing the token.
  if (status !== "authed" || !user) {
    return (
      <div className="flex flex-col gap-5" data-testid="invite-signed-out">
        <InviteSummary preview={invitation} />
        <Tabs defaultValue={invitation.requires_signup ? "register" : "login"}>
          <TabsList className="w-full">
            <TabsTrigger value="login">Sign in</TabsTrigger>
            <TabsTrigger value="register">Create account</TabsTrigger>
          </TabsList>
          <TabsContent value="login" className="pt-4">
            <LoginForm redirect={inviteHref} onSignedIn={() => undefined} />
          </TabsContent>
          <TabsContent value="register" className="pt-4">
            <RegisterForm
              defaultEmail={invitation.email}
              redirect={inviteHref}
            />
          </TabsContent>
        </Tabs>
      </div>
    )
  }

  // Signed in as the wrong person.
  if (user.email.toLowerCase() !== invitation.email.toLowerCase()) {
    return (
      <div className="flex flex-col gap-4" data-testid="invite-mismatch">
        <InviteSummary preview={invitation} />
        <Alert variant="destructive">
          <UserRoundXIcon />
          <AlertTitle>This invitation is for a different address</AlertTitle>
          <AlertDescription>
            It was sent to{" "}
            <span className="font-medium">{invitation.email}</span>, but you are
            signed in as <span className="font-medium">{user.email}</span>.
          </AlertDescription>
        </Alert>
        <Button
          variant="outline"
          onClick={async () => {
            await signOut({ queryClient })
            await navigate({ href: inviteHref })
          }}
        >
          Sign in as a different user
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4" data-testid="invite-accept">
      <InviteSummary preview={invitation} />
      <Button disabled={accept.isPending} onClick={() => accept.mutate()}>
        {accept.isPending ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <CheckIcon data-icon="inline-start" />
        )}
        Join {invitation.org_name}
      </Button>
    </div>
  )
}

function InviteAcceptPage() {
  const { token } = Route.useSearch()

  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 bg-muted/40 p-6">
      <Link to="/" className="text-lg font-semibold tracking-tight">
        TenderSense
      </Link>
      <AuthCard
        title="You are invited"
        description="Review the invitation before joining."
      >
        <InviteAcceptPanel token={token} />
      </AuthCard>
    </main>
  )
}
