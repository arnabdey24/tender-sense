import { useRef, useState } from "react"
import {
  ArrowDownIcon,
  DownloadIcon,
  FileTextIcon,
  GitBranchIcon,
} from "lucide-react"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardDescription,
} from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyMedia,
} from "@/components/ui/empty"
import type { AnalysisRequest, Artifact, Source } from "./schemas"

function safeUrl(value?: string | null) {
  try {
    const url = new URL(value ?? "")
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined
  } catch {
    return undefined
  }
}

export function Sources({ sources }: { sources: Source[] }) {
  return (
    <div className="flex flex-col gap-3">
      {sources.map((source) => (
        <details key={source.id} className="rounded-lg border p-3 text-xs">
          <summary className="cursor-pointer font-medium">
            {source.label}
          </summary>
          <blockquote className="mt-3 border-l-2 pl-3 whitespace-pre-wrap text-muted-foreground">
            {source.quote}
          </blockquote>
          {safeUrl(source.url) && (
            <a
              className="mt-3 inline-block underline underline-offset-4"
              href={safeUrl(source.url)}
              target="_blank"
              rel="noreferrer"
            >
              Open official notice ↗
            </a>
          )}
        </details>
      ))}
    </div>
  )
}

function download(text: string, name: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = document.createElement("a")
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function csvCell(value: unknown) {
  const text = String(value ?? "")
  // A downloaded label must not become a spreadsheet formula.
  return `"${(/^[=+@\-\t\r]/.test(text) ? "'" + text : text).replaceAll('"', '""')}"`
}

export default function ArtifactView({
  artifact,
  onAnalyze,
  busy,
}: {
  artifact: Artifact | null
  onAnalyze: (request: AnalysisRequest) => void
  busy: boolean
}) {
  const [percentage, setPercentage] = useState("15")
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const chartRef = useRef<HTMLDivElement>(null)
  if (!artifact)
    return (
      <Empty className="h-full">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <GitBranchIcon />
          </EmptyMedia>
          <EmptyTitle>A little room to think bigger</EmptyTitle>
          <EmptyDescription>
            Ask for a chart, calculation, or checklist. Your analysis will
            appear here, alongside the conversation.
          </EmptyDescription>
        </EmptyHeader>
        <Button
          variant="outline"
          onClick={() => onAnalyze({ kind: "capabilities" })}
          disabled={busy}
        >
          Explore capability fit
        </Button>
      </Empty>
    )
  const a = artifact
  const chart = a.rows.some((row) => row.value != null)
  const markdown = `# ${a.title}\n\n${a.description}\n\n${a.rows.map((row) => `- ${row.label}: ${row.value ?? ""} ${a.unit} ${row.detail}`).join("\n")}\n\n${a.formulas.join("\n")}\n\nAssumptions:\n${a.assumptions.join("\n")}\n\nSources:\n${a.sources.map((s) => `${s.label}: ${s.quote}${safeUrl(s.url) ? `\n${s.url}` : ""}`).join("\n\n")}`
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b px-5 py-3">
        <span className="text-xs font-medium tracking-wide text-muted-foreground">
          ANALYSIS WORKSPACE
        </span>
        <Badge variant="outline">Version {a.version}</Badge>
      </div>
      <div className="flex-1 overflow-y-auto p-5 md:p-8">
        <div className="mb-6 flex items-start justify-between gap-3">
          <div className="flex flex-col gap-2">
            <h2 className="text-xl font-semibold tracking-tight">{a.title}</h2>
            <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
              {a.description}
            </p>
          </div>
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Download analysis as Markdown"
            onClick={() =>
              download(
                markdown,
                `${a.kind}-v${a.version}.md`,
                "text/markdown;charset=utf-8"
              )
            }
          >
            <DownloadIcon />
          </Button>
        </div>
        <Tabs defaultValue="visual" key={`${a.id}:${a.version}`}>
          <TabsList variant="line">
            <TabsTrigger value="visual">
              {chart ? "Chart" : "Overview"}
            </TabsTrigger>
            <TabsTrigger value="data">Data</TabsTrigger>
            <TabsTrigger value="calculation">Calculation</TabsTrigger>
            <TabsTrigger value="sources">Sources</TabsTrigger>
          </TabsList>
          <TabsContent value="visual" className="pt-5">
            {chart ? (
              <div ref={chartRef} className="flex flex-col gap-4">
                <ChartContainer
                  config={{
                    value: {
                      label: a.kind === "scenario" ? "Scenario" : "Similarity",
                      color: "var(--chart-1)",
                    },
                    baseline: { label: "Current", color: "var(--chart-3)" },
                  }}
                  className="aspect-auto h-72 w-full"
                >
                  <BarChart
                    accessibilityLayer
                    data={a.rows}
                    layout="vertical"
                    margin={{ left: 0, right: 25 }}
                  >
                    <CartesianGrid horizontal={false} />
                    <YAxis
                      dataKey="label"
                      type="category"
                      width={135}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 11 }}
                    />
                    <XAxis
                      type="number"
                      domain={a.unit === "similarity" ? [-1, 1] : [0, "auto"]}
                      tickLine={false}
                      axisLine={false}
                    />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    {a.kind === "scenario" && (
                      <Bar
                        dataKey="baseline"
                        fill="var(--color-baseline)"
                        radius={4}
                        isAnimationActive={false}
                      />
                    )}
                    <Bar
                      dataKey="value"
                      fill="var(--color-value)"
                      radius={4}
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ChartContainer>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    {a.unit || "Recorded value"}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const svg = chartRef.current?.querySelector("svg")
                      if (svg) {
                        const clone = svg.cloneNode(true) as SVGElement
                        clone.setAttribute(
                          "xmlns",
                          "http://www.w3.org/2000/svg"
                        )
                        clone.setAttribute(
                          "style",
                          "--color-value:#39756b;--color-baseline:#8f9ba8;--muted-foreground:#64748b;--border:#cbd5e1;color:#1e293b;background:white"
                        )
                        download(
                          new XMLSerializer().serializeToString(clone),
                          `${a.kind}.svg`,
                          "image/svg+xml"
                        )
                      }
                    }}
                  >
                    Download SVG
                  </Button>
                </div>
              </div>
            ) : a.rows.length ? (
              <div className="flex flex-col gap-3">
                {a.rows.map((row, i) => (
                  <div key={`${row.label}:${i}`}>
                    <Card size="sm">
                      <CardHeader>
                        <CardTitle className="flex items-center justify-between gap-3">
                          {a.kind === "checklist" ? (
                            <label className="flex items-center gap-3">
                              <Checkbox
                                checked={checked[`${a.version}:${i}`] ?? false}
                                onCheckedChange={(value) =>
                                  setChecked((old) => ({
                                    ...old,
                                    [`${a.version}:${i}`]: Boolean(value),
                                  }))
                                }
                              />
                              {row.label}
                            </label>
                          ) : (
                            row.label
                          )}
                          {row.status && (
                            <Badge variant="outline">
                              {row.status === "unknown"
                                ? "Needs checking"
                                : row.status}
                            </Badge>
                          )}
                        </CardTitle>
                        <CardDescription>{row.detail}</CardDescription>
                      </CardHeader>
                    </Card>
                    {a.kind === "eligibility" && i < a.rows.length - 1 && (
                      <ArrowDownIcon className="mx-auto mt-3 size-4 text-muted-foreground" />
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <FileTextIcon />
                  </EmptyMedia>
                  <EmptyTitle>More information needed</EmptyTitle>
                  <EmptyDescription>{a.assumptions.at(-1)}</EmptyDescription>
                </EmptyHeader>
              </Empty>
            )}
            {a.kind === "scenario" && (
              <form
                className="mt-6 flex items-end gap-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  onAnalyze({
                    kind: "scenario",
                    adjustment_percent: Number(percentage),
                  })
                }}
              >
                <Field>
                  <FieldLabel htmlFor="scenario-percentage">
                    Hypothetical turnover change (%)
                  </FieldLabel>
                  <Input
                    id="scenario-percentage"
                    type="number"
                    min={-100}
                    max={500}
                    step="0.1"
                    value={percentage}
                    onChange={(e) => setPercentage(e.target.value)}
                    required
                  />
                </Field>
                <Button type="submit" variant="outline" disabled={busy}>
                  Recalculate
                </Button>
              </form>
            )}
          </TabsContent>
          <TabsContent value="data" className="pt-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Item</TableHead>
                  <TableHead>Value / evidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {a.rows.map((row, i) => (
                  <TableRow key={i}>
                    <TableCell className="whitespace-normal">
                      {row.label}
                    </TableCell>
                    <TableCell className="whitespace-normal">
                      {row.value != null
                        ? `${row.value} ${a.unit}`
                        : row.detail}
                      {row.baseline != null && (
                        <p className="text-xs text-muted-foreground">
                          Current: {row.baseline}
                        </p>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Button
              className="mt-4"
              variant="outline"
              size="sm"
              onClick={() =>
                download(
                  [
                    "Item,Value,Unit,Current,Detail",
                    ...a.rows.map((row) =>
                      [row.label, row.value, a.unit, row.baseline, row.detail]
                        .map(csvCell)
                        .join(",")
                    ),
                  ].join("\r\n"),
                  `${a.kind}.csv`,
                  "text/csv;charset=utf-8"
                )
              }
            >
              Download CSV
            </Button>
          </TabsContent>
          <TabsContent value="calculation" className="pt-5">
            <Card>
              <CardHeader>
                <CardTitle>Check the calculation</CardTitle>
                <CardDescription>
                  Recorded inputs and deterministic arithmetic.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                {a.formulas.length ? (
                  a.formulas.map((formula, i) => (
                    <code
                      key={i}
                      className="block rounded-md bg-muted p-4 text-xs leading-relaxed whitespace-pre-wrap"
                    >
                      {formula}
                    </code>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No reproducible numerical calculation is available for this
                    view.
                  </p>
                )}
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="sources" className="pt-5">
            <Sources sources={a.sources} />
          </TabsContent>
        </Tabs>
        {a.assumptions.length > 0 && (
          <div className="mt-8 border-t pt-4">
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              ASSUMPTIONS & LIMITS
            </p>
            <ul className="flex list-disc flex-col gap-2 pl-4 text-xs leading-relaxed text-muted-foreground">
              {a.assumptions.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        <p className="mt-6 text-xs text-muted-foreground">
          Generated {new Date(a.created_at).toLocaleString()} · Context{" "}
          {a.context_version.slice(0, 8)}
        </p>
      </div>
    </div>
  )
}
