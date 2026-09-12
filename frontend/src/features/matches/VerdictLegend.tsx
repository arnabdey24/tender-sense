import { InfoIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  GRADE_MEANINGS,
  bandLabel,
  type GradeThresholds,
} from "@/features/matches/grades"
import { GradeBadge } from "@/features/tenders/GradeBadge"
import { EligibilityBadge } from "@/features/matches/verdict"

const GRADES = ["S", "A", "B", "C"] as const

/**
 * What the letters mean, said somewhere.
 *
 * Every list in the product marks notices S, A, B or C, and the vocabulary was
 * defined nowhere — not on the badge, not on the feed, not on the chart that
 * plots the distribution of them. A grading scheme whose scale is private is
 * a number the reader has to guess at, and the guesses are the dangerous part:
 * "S" invites reading as a probability of winning, which it is not.
 *
 * "Needs checking" has the same problem and a worse failure mode. It sits on a
 * dashboard tab as a count with no definition, and the two wrong readings —
 * "the system failed" and "we are not eligible" — both stop somebody acting on
 * a notice they are probably eligible for. It means the opposite: the rules
 * could not be decided from the notice, and a human has to look.
 *
 * A popover rather than a tooltip. This is reference text, read once or twice
 * and then never again, and a tooltip cannot be opened on a touch screen at
 * all.
 */
export function VerdictLegend({
  thresholds,
  className,
}: {
  thresholds: GradeThresholds
  className?: string
}) {
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="xs" className={className}>
            <InfoIcon data-icon="inline-start" />
            What the grades mean
          </Button>
        }
      />
      <PopoverContent align="start" className="w-80 gap-3">
        <div className="flex flex-col gap-0.5">
          <PopoverTitle className="text-sm font-medium">
            How a tender is graded
          </PopoverTitle>
          <PopoverDescription className="text-xs text-muted-foreground text-pretty">
            How closely the notice resembles your capability profile. It is not
            a probability of winning, and it says nothing about whether you are
            eligible.
          </PopoverDescription>
        </div>

        <dl className="flex flex-col gap-2">
          {GRADES.map((grade) => (
            <div key={grade} className="flex items-start gap-2">
              <dt className="shrink-0 pt-0.5">
                <GradeBadge grade={grade} className="w-7 justify-center" />
              </dt>
              <dd className="min-w-0 text-xs">
                <span className="text-pretty">{GRADE_MEANINGS[grade]}</span>{" "}
                <span className="whitespace-nowrap text-muted-foreground tabular-nums">
                  ({bandLabel(grade, thresholds)})
                </span>
              </dd>
            </div>
          ))}
        </dl>

        <div className="flex flex-col gap-2 border-t pt-2.5">
          <PopoverDescription className="text-xs font-medium text-foreground">
            Eligibility is judged separately
          </PopoverDescription>
          <dl className="flex flex-col gap-2">
            <div className="flex items-start gap-2">
              <dt className="shrink-0 pt-0.5">
                <EligibilityBadge status="eligible" />
              </dt>
              <dd className="min-w-0 text-xs text-pretty">
                Every rule you set was checked against the notice and passed.
              </dd>
            </div>
            <div className="flex items-start gap-2">
              <dt className="shrink-0 pt-0.5">
                <EligibilityBadge status="needs_verification" />
              </dt>
              <dd className="min-w-0 text-xs text-pretty">
                The notice did not state something a rule needs, so nobody can
                decide it from the notice alone. Not a rejection — it is the
                queue of tenders waiting on a human to look.
              </dd>
            </div>
            <div className="flex items-start gap-2">
              <dt className="shrink-0 pt-0.5">
                <EligibilityBadge status="ineligible" />
              </dt>
              <dd className="min-w-0 text-xs text-pretty">
                A rule failed outright on something the notice does state.
              </dd>
            </div>
          </dl>
        </div>
      </PopoverContent>
    </Popover>
  )
}
