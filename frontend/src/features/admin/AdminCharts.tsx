import * as React from "react"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import type { AiUsageSummary, Trends } from "@/features/admin/api"

/**
 * Three questions a counter cannot answer.
 *
 * Every figure on this console is an instant — 146 notices held, 271 failures,
 * 0% of budget — and none of them says whether that is where it was yesterday.
 * A portal that has quietly stopped answering still reports a pool size; only
 * the shape of the intake gives it away. So these are not decoration, and they
 * are deliberately not a chart wall on a landing page: each one sits inside the
 * section whose numbers it explains.
 *
 * Restraint on purpose. Compact height, one grid line family, no gradient, no
 * tinted panel. Grade colours are never borrowed here — those are the product's
 * grading vocabulary and reusing them as a series would teach the wrong thing.
 */

/** A 14-point axis cannot show 14 labels, so it shows the ends and the weeks. */
function dayTick(value: React.ReactNode): string {
  const text = String(value ?? "")
  const date = new Date(`${text}T00:00:00Z`)
  return Number.isNaN(date.getTime())
    ? text
    : date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      })
}

/**
 * Thousands as `2.2k`.
 *
 * A busy deployment runs thousands of jobs a day and spends hundreds of
 * thousands of tokens, and a four- or six-digit tick either clips against the
 * axis or eats the width the plot needed. The exact figure is one hover away
 * and in the written summary; the axis only has to give the scale.
 */
/**
 * A bar is a bar, not a billboard.
 *
 * Recharts divides the plot between however many categories it has, so a
 * deployment two days old — which is every deployment on its second day — drew
 * two bars each taking half the width. Capping keeps the shape readable while
 * the history fills in behind it.
 */
const MAX_BAR = 48

function compactTick(value: number): string {
  if (!Number.isFinite(value)) return ""
  if (Math.abs(value) >= 1_000_000) return `${+(value / 1_000_000).toFixed(1)}m`
  if (Math.abs(value) >= 1_000) return `${+(value / 1_000).toFixed(1)}k`
  return String(value)
}

const SERIES_COLOURS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-5)",
  "var(--chart-4)",
]

function Frame({
  title,
  hint,
  summary,
  children,
}: {
  title: string
  hint: string
  /** What the chart says, for a reader who cannot see it. */
  summary: string
  children: React.ReactNode
}) {
  const id = React.useId()

  /*
    Named and described, not hidden.

    Hiding the plot with `aria-hidden` was the reflex and it was wrong twice
    over: it puts an `aria-hidden` ancestor over the focusable surface Recharts
    renders, which is a WCAG failure on its own, and it throws away the keyboard
    layer that surface exists for — arrow keys walk the series and announce each
    day's figures. So the plot stays in the tree, the caption names it, and the
    summary gives the shape a reader arrowing through one point at a time would
    otherwise have to assemble for themselves.
  */
  return (
    <figure
      className="min-w-0"
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-summary`}
    >
      <figcaption
        id={`${id}-title`}
        className="flex flex-wrap items-baseline gap-x-2"
      >
        <span className="text-sm font-medium">{title}</span>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </figcaption>
      <p id={`${id}-summary`} className="sr-only">
        {summary}
      </p>
      <div className="mt-3">{children}</div>
    </figure>
  )
}

function Quiet({ children }: { children: React.ReactNode }) {
  return <p className="py-6 text-sm text-muted-foreground">{children}</p>
}

const AXIS = {
  tickLine: false,
  axisLine: false,
  className: "text-[11px] fill-muted-foreground",
} as const

/**
 * Notices arriving, per portal, per day.
 *
 * The section this sits in says "a pool that stops growing is the first symptom
 * of a portal that has stopped answering". This is that sentence drawn: a
 * portal that goes silent loses its band, and the gap is visible at a glance in
 * a way that a column of last-success timestamps never is.
 *
 * Stacked rather than grouped, because the first question is whether the pool
 * is still filling at all; which portal filled it is the second, and the
 * stack answers both without doubling the width.
 */
export function PoolIntakeChart({
  trends,
  isLoading,
}: {
  trends?: Trends
  isLoading?: boolean
}) {
  if (isLoading) return <Skeleton className="h-44 w-full rounded-lg" />
  if (!trends) return null

  const codes = trends.sources ?? []
  const names = trends.source_names ?? {}
  const rows: Record<string, string | number>[] = (trends.intake ?? []).map(
    (point) => ({ day: point.day, ...(point.by_source ?? {}) })
  )
  const total = rows.reduce(
    (sum, row) =>
      sum + codes.reduce((n, code) => n + (Number(row[code]) || 0), 0),
    0
  )

  const config: ChartConfig = Object.fromEntries(
    codes.map((code, index) => [
      code,
      {
        label: names[code] ?? code,
        color: SERIES_COLOURS[index % SERIES_COLOURS.length],
      },
    ])
  )

  const latest = rows.at(-1)
  const summary = total
    ? `${total.toLocaleString()} notices arrived over the last ${trends.days} days. ` +
      codes
        .map((code) => `${names[code] ?? code}: ${Number(latest?.[code]) || 0} today`)
        .join(", ")
    : `No notices have arrived in the last ${trends.days} days.`

  return (
    <Frame
      title="Arrivals"
      hint={`Notices added per day, by portal, over ${trends.days} days.`}
      summary={summary}
    >
      {total === 0 ? (
        <Quiet>
          Nothing has arrived in {trends.days} days. Either every portal is
          silent or none has been pulled — the runs table below says which.
        </Quiet>
      ) : (
        <ChartContainer config={config} className="aspect-auto h-44 w-full">
          <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} className="stroke-border" />
            <XAxis
              dataKey="day"
              tickFormatter={dayTick}
              interval="preserveStartEnd"
              minTickGap={24}
              tickMargin={8}
              {...AXIS}
            />
            <YAxis width={44} allowDecimals={false} tickFormatter={compactTick} {...AXIS} />
            <ChartTooltip content={<ChartTooltipContent labelFormatter={dayTick} />} />
            <ChartLegend content={<ChartLegendContent />} />
            {codes.map((code, index) => (
              <Bar
                key={code}
                dataKey={code}
                stackId="intake"
                fill={`var(--color-${code})`}
                // Only the top of the stack is rounded, so the bands read as
                // one bar rather than as separate floating chips.
                maxBarSize={MAX_BAR}
                radius={index === codes.length - 1 ? [3, 3, 0, 0] : 0}
              />
            ))}
          </BarChart>
        </ChartContainer>
      )}
    </Frame>
  )
}

const JOB_SERIES = [
  { key: "succeeded", label: "Succeeded", color: "var(--success)" },
  { key: "partial", label: "Partial", color: "var(--warning)" },
  { key: "failed", label: "Failed", color: "var(--destructive)" },
] as const

const jobConfig: ChartConfig = Object.fromEntries(
  JOB_SERIES.map((s) => [s.key, { label: s.label, color: s.color }])
)

/**
 * Background work, by outcome, per day.
 *
 * "271 failed in 24h" is the number the front page gives, and it cannot
 * distinguish a burst that ended eight hours ago from a failure that is still
 * running — which are different emergencies. The shape says which.
 *
 * Colour is meaning here rather than series identity, so these are the status
 * tokens and not the chart ramp: green work, amber partial, red lost.
 */
export function JobOutcomeChart({
  trends,
  isLoading,
}: {
  trends?: Trends
  isLoading?: boolean
}) {
  if (isLoading) return <Skeleton className="h-44 w-full rounded-lg" />
  if (!trends) return null

  const rows = trends.jobs ?? []
  const totals = JOB_SERIES.map((series) => ({
    ...series,
    total: rows.reduce((n, row) => n + (Number(row[series.key]) || 0), 0),
  }))
  const any = totals.some((t) => t.total > 0)
  const latest = rows.at(-1)

  const summary = any
    ? `Over ${trends.days} days: ` +
      totals.map((t) => `${t.total.toLocaleString()} ${t.label.toLowerCase()}`).join(", ") +
      `. Today: ${Number(latest?.failed) || 0} failed of ${
        (Number(latest?.succeeded) || 0) +
        (Number(latest?.partial) || 0) +
        (Number(latest?.failed) || 0)
      }.`
    : `No background jobs have run in the last ${trends.days} days.`

  return (
    <Frame
      title="Outcomes"
      hint={`Runs per day over ${trends.days} days, by how they ended.`}
      summary={summary}
    >
      {!any ? (
        <Quiet>
          No job has run in {trends.days} days. A schedule that has stopped
          looks exactly like this.
        </Quiet>
      ) : (
        <ChartContainer config={jobConfig} className="aspect-auto h-44 w-full">
          <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} className="stroke-border" />
            <XAxis
              dataKey="day"
              tickFormatter={dayTick}
              interval="preserveStartEnd"
              minTickGap={24}
              tickMargin={8}
              {...AXIS}
            />
            <YAxis width={44} allowDecimals={false} tickFormatter={compactTick} {...AXIS} />
            <ChartTooltip content={<ChartTooltipContent labelFormatter={dayTick} />} />
            <ChartLegend content={<ChartLegendContent />} />
            {JOB_SERIES.map((s, index) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                stackId="runs"
                fill={`var(--color-${s.key})`}
                maxBarSize={MAX_BAR}
                radius={index === JOB_SERIES.length - 1 ? [3, 3, 0, 0] : 0}
              />
            ))}
          </BarChart>
        </ChartContainer>
      )}
    </Frame>
  )
}

/** Turn `purpose` into something a person reads. */
function purposeLabel(key: string): string {
  const words = key.replace(/[_-]+/g, " ").trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/**
 * Tokens per day, by what spent them.
 *
 * This replaces a twelve-row table of day-and-purpose pairs. The table held
 * the same figures and could not answer the question anybody asks of them —
 * whether today is unusual, and which kind of work is responsible. A budget
 * that empties at four in the afternoon is a different problem from one that
 * has been climbing all week.
 */
export function SpendChart({
  usage,
  isLoading,
}: {
  usage?: AiUsageSummary
  isLoading?: boolean
}) {
  if (isLoading) return <Skeleton className="h-44 w-full rounded-lg" />

  const rows = usage?.rows ?? []
  if (rows.length === 0) {
    return (
      <Quiet>
        No model calls recorded yet. Spend appears here once matching or the
        assistant has run.
      </Quiet>
    )
  }

  const purposes = [...new Set(rows.map((row) => row.purpose))].sort()
  const byDay = new Map<string, Record<string, number | string>>()
  for (const row of rows) {
    const day = String(row.day)
    const entry = byDay.get(day) ?? { day }
    entry[row.purpose] =
      (Number(entry[row.purpose]) || 0) + row.tokens_in + row.tokens_out
    byDay.set(day, entry)
  }
  const data = [...byDay.values()].sort(
    (a, b) => String(a.day).localeCompare(String(b.day))
  )

  const config: ChartConfig = Object.fromEntries(
    purposes.map((purpose, index) => [
      purpose,
      {
        label: purposeLabel(purpose),
        color: SERIES_COLOURS[index % SERIES_COLOURS.length],
      },
    ])
  )

  const total = rows.reduce((n, row) => n + row.tokens_in + row.tokens_out, 0)
  const summary =
    `${total.toLocaleString()} tokens over ${data.length} days, spent on ` +
    purposes.map(purposeLabel).join(", ") +
    `. Today: ${(usage?.spent_today ?? 0).toLocaleString()}.`

  return (
    <Frame
      title="Where the tokens went"
      hint="Daily spend, by the work that caused it."
      summary={summary}
    >
      <ChartContainer config={config} className="aspect-auto h-44 w-full">
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} className="stroke-border" />
          <XAxis
            dataKey="day"
            tickFormatter={dayTick}
            interval="preserveStartEnd"
            minTickGap={24}
            tickMargin={8}
            {...AXIS}
          />
          <YAxis
            width={44}
            allowDecimals={false}
            tickFormatter={compactTick}
            {...AXIS}
          />
          <ChartTooltip content={<ChartTooltipContent labelFormatter={dayTick} />} />
          <ChartLegend content={<ChartLegendContent />} />
          {purposes.map((purpose, index) => (
            <Bar
              key={purpose}
              dataKey={purpose}
              stackId="spend"
              fill={`var(--color-${purpose})`}
              maxBarSize={MAX_BAR}
              radius={index === purposes.length - 1 ? [3, 3, 0, 0] : 0}
            />
          ))}
        </BarChart>
      </ChartContainer>
    </Frame>
  )
}
