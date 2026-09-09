import { createFileRoute } from "@tanstack/react-router"

import { ComingSoon } from "@/components/layout/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export const Route = createFileRoute("/_app/app/tenders/")({
  component: Page,
})

function Page() {
  return (
    <>
      <PageHeader
        title="Tenders"
        description="Browse and grade discovered tenders."
      />
      <ComingSoon />
    </>
  )
}
