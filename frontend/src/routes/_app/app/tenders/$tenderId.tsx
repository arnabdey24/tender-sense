import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowLeftIcon } from "lucide-react"

import { ComingSoon } from "@/components/layout/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { GradeBadge } from "@/features/tenders/GradeBadge"

export const Route = createFileRoute("/_app/app/tenders/$tenderId")({
  component: TenderDetailPage,
})

function TenderDetailPage() {
  const { tenderId } = Route.useParams()

  return (
    <>
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            Tender {tenderId}
            <GradeBadge grade="A" />
          </span>
        }
        description="Full tender detail, documents, and grading rationale."
        actions={
          <Button
            variant="outline"
            render={<Link to="/app/tenders" />}
            nativeButton={false}
          >
            <ArrowLeftIcon data-icon="inline-start" />
            All tenders
          </Button>
        }
      />
      <ComingSoon />
    </>
  )
}
