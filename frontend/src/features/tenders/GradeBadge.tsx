import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

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

export function GradeBadge({ grade, className, ...props }: GradeBadgeProps) {
  return (
    <Badge
      variant={VARIANT_BY_GRADE[grade]}
      // A pill with one centred capital is an avatar's shape, and it sat beside
      // real initials avatars in the same lists. A grade is a mark on a notice,
      // not a person, so it takes the squarer corner the rest of the system uses.
      className={cn("rounded-md font-semibold", className)}
      aria-label={`Grade ${grade}`}
      data-grade={grade}
      {...props}
    >
      {grade}
    </Badge>
  )
}
