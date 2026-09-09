import { createFileRoute } from "@tanstack/react-router"

import { ComingSoon } from "@/components/layout/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export const Route = createFileRoute("/_app/app/pipeline")({
  component: Page,
})

function Page() {
  return (
    <>
      <PageHeader
        title="Pipeline"
        description="Track opportunities from shortlist to submission."
      />
      <ComingSoon />
    </>
  )
}
