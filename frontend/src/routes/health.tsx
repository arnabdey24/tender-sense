import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { ActivityIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api/client"
import { normalizeError } from "@/lib/api/errors"
import { qk } from "@/lib/api/query-keys"

export const Route = createFileRoute("/health")({
  component: HealthPage,
})

async function fetchHealth() {
  const { data, error, response } = await api.GET("/api/v1/health/live")
  if (error || !data) throw normalizeError(response, error)
  return data
}

function HealthPage() {
  const query = useQuery({ queryKey: qk.health(), queryFn: fetchHealth })

  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ActivityIcon className="text-muted-foreground" />
            API health
          </CardTitle>
          <CardDescription>
            Calls <code>/api/v1/health/live</code> through the typed client and
            the Vite dev proxy.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {query.isPending ? <Skeleton className="h-5 w-24" /> : null}
          {query.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Request failed</AlertTitle>
              <AlertDescription>{query.error.message}</AlertDescription>
            </Alert>
          ) : null}
          {query.isSuccess ? (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">status</span>
              <Badge
                variant={query.data.status === "ok" ? "success" : "warning"}
              >
                {query.data.status}
              </Badge>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </main>
  )
}
