import { createFileRoute } from "@tanstack/react-router"

import { ComingSoon } from "@/components/layout/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export const Route = createFileRoute("/_app/app/notifications")({
  component: Page,
})

function Page() {
  return (
    <>
      <PageHeader
        title="Notifications"
        description="Alerts about new matches and deadlines."
      />
      <ComingSoon />
    </>
  )
}
