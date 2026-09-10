import { Bar, BarChart, Cell, LabelList, XAxis, YAxis } from "recharts"

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import type { MatchStats } from "@/features/matches/api"

/**
 * Two questions a count cannot answer.
 *
 * "23 open matches" says nothing about when the work lands or whether the
 * profile is finding anything, which are the two things worth knowing before
 * opening the queue. Both come from `by_urgency` and `by_grade`, already on
 * the stats payload — neither chart costs a request.
 *
 * Deliberately below the queue, not above it: these describe the pool, they
 * are not the day's decisions.
 */

/** Urgency is ordinal, so it is drawn in time order, not by size. */
const RUNWAY = [
  { key: "expired", label: "Overdue" },
  { key: "critical", label: "≤3d" },
  { key: "high", label: "≤7d" },
  { key: "normal", label: "≤21d" },
  { key: "low", label: "Later" },
  { key: "unknown", label: "No date" },
] as const

const GRADES = [
  { key: "S", label: "S", fill: "var(--grade-s)" },
  { key: "A", label: "A", fill: "var(--grade-a)" },
  { key: "B", label: "B", fill: "var(--grade-b)" },
  { key: "C", label: "C", fill: "var(--grade-c)" },
] as const

const runwayConfig = {
  count: { label: "Matches", color: "var(--chart-1)" },
} satisfies ChartConfig

const gradeConfig = {
  count: { label: "Matches" },
} satisfies ChartConfig

function Panel({
  title,
  hint,
  children,
}: {
  title: string
  hint: string
  children: React.ReactNode
}) {
  return (
    <section className="min-w-0 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <h3 className="font-heading text-sm font-medium">{title}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
      <div className="mt-3">{children}</div>
    </section>
  )
}

export function MatchCharts({
  stats,
  isLoading,
}: {
  stats?: MatchStats
  isLoading?: boolean
}) {
  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-52 rounded-xl" />
        <Skeleton className="h-52 rounded-xl" />
      </div>
    )
  }

  const runway = RUNWAY.map((bucket) => ({
    label: bucket.label,
    count: stats?.by_urgency?.[bucket.key] ?? 0,
  }))
  const grades = GRADES.map((grade) => ({
    label: grade.label,
    fill: grade.fill,
    count: stats?.by_grade?.[grade.key] ?? 0,
  }))

  // Every bucket empty means there is nothing to describe, and an axis with
  // six zeroes on it describes nothing.
  if (runway.every((r) => r.count === 0) && grades.every((g) => g.count === 0)) {
    return null
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel
        title="Deadline runway"
        hint="When the open matches close, so the week can be planned."
      >
        <ChartContainer
          config={runwayConfig}
          className="aspect-auto h-40 w-full"
        >
          <BarChart data={runway} margin={{ top: 14, right: 4, bottom: 0, left: 4 }}>
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
            />
            <YAxis hide />
            <ChartTooltip content={<ChartTooltipContent hideLabel={false} />} />
            <Bar dataKey="count" fill="var(--color-count)" radius={[4, 4, 0, 0]}>
              {/* Direct labels rather than a y-axis: six numbers read faster
                  than a scale the reader has to map back onto the bars. */}
              <LabelList
                dataKey="count"
                position="top"
                offset={6}
                className="fill-foreground text-[11px] font-medium"
              />
            </Bar>
          </BarChart>
        </ChartContainer>
      </Panel>

      <Panel
        title="Grade mix"
        hint="Whether the capability profile is finding strong fits at all."
      >
        <ChartContainer config={gradeConfig} className="aspect-auto h-40 w-full">
          <BarChart
            data={grades}
            layout="vertical"
            margin={{ top: 0, right: 26, bottom: 0, left: 4 }}
          >
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="label"
              tickLine={false}
              axisLine={false}
              width={20}
              className="font-medium"
            />
            <ChartTooltip content={<ChartTooltipContent hideLabel={false} />} />
            {/* `minPointSize` keeps a zero row from rendering as nothing at
                all, which read as a chart that had failed to load rather than
                a grade with no matches in it. */}
            <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={18} minPointSize={2}>
              {/* The grading vocabulary drawn as itself, with the letter on
                  the axis — colour is not carrying this alone. */}
              {grades.map((grade) => (
                <Cell key={grade.label} fill={grade.fill} />
              ))}
              <LabelList
                dataKey="count"
                position="right"
                offset={6}
                className="fill-foreground text-[11px] font-medium"
              />
            </Bar>
          </BarChart>
        </ChartContainer>
      </Panel>
    </div>
  )
}
