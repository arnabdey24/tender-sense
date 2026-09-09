import { createFileRoute } from "@tanstack/react-router"

import { ComingSoon } from "@/components/layout/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export const Route = createFileRoute("/_app/app/today")({
  component: Page,
})

function Page() {
  return (
    <>
      <PageHeader
        title="Today"
        description="Deadlines and actions due today."
      />
      <ComingSoon />
    </>
  )
}
