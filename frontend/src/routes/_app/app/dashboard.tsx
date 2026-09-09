import { createFileRoute } from "@tanstack/react-router"

import { ComingSoon } from "@/components/layout/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export const Route = createFileRoute("/_app/app/dashboard")({
  component: Page,
})

function Page() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your tender activity at a glance."
      />
      <ComingSoon />
    </>
  )
}
