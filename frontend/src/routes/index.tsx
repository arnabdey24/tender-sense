import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRightIcon } from "lucide-react"

import { Button } from "@/components/ui/button"

export const Route = createFileRoute("/")({
  component: LandingPage,
})

function LandingPage() {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-8 px-6 text-center">
      <div className="flex max-w-xl flex-col gap-4">
        <h1 className="text-5xl font-semibold tracking-tight">TenderSense</h1>
        <p className="text-lg text-muted-foreground">
          Find, grade, and win the public tenders that matter to your business.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button size="lg" render={<Link to="/login" />} nativeButton={false}>
          Sign in
        </Button>
        <Button
          size="lg"
          variant="outline"
          render={<Link to="/register" />}
          nativeButton={false}
        >
          Create account
          <ArrowRightIcon data-icon="inline-end" />
        </Button>
      </div>
    </main>
  )
}
