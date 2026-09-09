import {
  Link,
  useRouter,
  type ErrorComponentProps,
} from "@tanstack/react-router"
import { AlertTriangleIcon, RotateCcwIcon, SearchXIcon } from "lucide-react"

import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"

export function DefaultNotFound() {
  return (
    <Empty className="min-h-svh">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <SearchXIcon />
        </EmptyMedia>
        <EmptyTitle>Page not found</EmptyTitle>
        <EmptyDescription>
          The page you are looking for does not exist or has moved.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button render={<Link to="/" />} nativeButton={false}>
          Back to home
        </Button>
      </EmptyContent>
    </Empty>
  )
}

export function DefaultError({ error, reset }: ErrorComponentProps) {
  const router = useRouter()
  const message =
    error instanceof Error ? error.message : "An unexpected error occurred."

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <Alert variant="destructive" className="max-w-lg">
        <AlertTriangleIcon />
        <AlertTitle>Something went wrong</AlertTitle>
        <AlertDescription>{message}</AlertDescription>
        <AlertAction>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              reset()
              void router.invalidate()
            }}
          >
            <RotateCcwIcon data-icon="inline-start" />
            Retry
          </Button>
        </AlertAction>
      </Alert>
    </div>
  )
}
