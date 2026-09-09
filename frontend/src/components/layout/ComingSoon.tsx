import { ConstructionIcon } from "lucide-react"

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"

export function ComingSoon({
  description = "This area is under construction and will land in a later milestone.",
}: {
  description?: string
}) {
  return (
    <Empty className="flex-1">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <ConstructionIcon />
        </EmptyMedia>
        <EmptyTitle>Coming soon</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}
