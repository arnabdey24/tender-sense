import { Badge } from "@/components/ui/badge"

export type TenderGrade = "S" | "A" | "B" | "C"

const VARIANT_BY_GRADE = {
  S: "gradeS",
  A: "gradeA",
  B: "gradeB",
  C: "gradeC",
} as const

export type GradeBadgeProps = Omit<
  React.ComponentProps<typeof Badge>,
  "variant" | "children"
> & {
  grade: TenderGrade
}

export function GradeBadge({ grade, ...props }: GradeBadgeProps) {
  return (
    <Badge
      variant={VARIANT_BY_GRADE[grade]}
      aria-label={`Grade ${grade}`}
      data-grade={grade}
      {...props}
    >
      {grade}
    </Badge>
  )
}
