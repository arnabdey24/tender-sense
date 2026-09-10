import { createFileRoute } from "@tanstack/react-router"
import { PlayIcon, PlusIcon, RotateCcwIcon, SaveIcon } from "lucide-react"
import * as React from "react"

import { PageHeader } from "@/components/layout/PageHeader"
import { PageBody, PageSection } from "@/components/layout/PageSection"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { RuleRow } from "@/features/rules/RuleRow"
import {
  useActivateVersion,
  usePreviewRules,
  useRuleCatalogue,
  useRuleSet,
  useRuleSetVersions,
  useSaveRuleSet,
  type CataloguePreset,
  type RuleDefinition,
} from "@/features/rules/api"
import { useIsOrgAdmin } from "@/lib/auth/store"

export const Route = createFileRoute("/_app/app/settings/rules")({
  component: RulesPage,
})

/** Stable-ish id for a new row; the backend only needs it to be unique. */
function newRuleId(attribute: string, existing: RuleDefinition[]): string {
  const base = `r_${attribute}`
  if (!existing.some((r) => r.id === base)) return base
  return `${base}_${existing.length + 1}`
}

function ruleFromPreset(
  preset: CataloguePreset,
  existing: RuleDefinition[]
): RuleDefinition {
  return {
    id: newRuleId(preset.attribute, existing),
    attribute: preset.attribute,
    operator: preset.operator,
    value: preset.value as RuleDefinition["value"],
    severity: preset.severity,
    on_missing: preset.on_missing,
    enabled: true,
    label: preset.label,
    template: preset.key,
  }
}

function PreviewPanel({
  preview,
  rules,
}: {
  preview: ReturnType<typeof usePreviewRules>
  rules: RuleDefinition[]
}) {
  if (preview.isPending && !preview.data) return null
  const data = preview.data
  if (!data) return null

  const counts = data.counts
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Badge variant="secondary">{counts?.evaluated ?? 0} checked</Badge>
        <Badge variant="success">{counts?.eligible ?? 0} eligible</Badge>
        <Badge variant="warning">
          {counts?.needs_verification ?? 0} need checking
        </Badge>
        <Badge variant="destructive">{counts?.ineligible ?? 0} excluded</Badge>
      </div>

      {/* Per-rule counts are the useful part: they name the line to relax. */}
      <div className="flex flex-col gap-1">
        {rules.map((rule) => {
          const bucket = data.per_rule?.[rule.id]
          if (!bucket) return null
          return (
            <div
              key={rule.id}
              className="flex items-center justify-between gap-2 text-sm"
            >
              <span className="truncate">{rule.label || rule.attribute}</span>
              <span className="shrink-0 text-muted-foreground tabular-nums">
                {bucket.ineligible ?? 0} excluded ·{" "}
                {bucket.needs_verification ?? 0} to check
              </span>
            </div>
          )
        })}
      </div>

      {data.samples?.length ? (
        <div className="flex flex-col gap-1">
          <h3 className="text-xs text-muted-foreground">
            Tenders this would hold back
          </h3>
          <ul className="flex flex-col gap-1 text-sm">
            {data.samples.map((sample) => (
              <li key={sample.tender_id} className="flex flex-col">
                <span className="truncate">{sample.title}</span>
                <span className="text-xs text-muted-foreground">
                  {[
                    ...(sample.failing_rules ?? []),
                    ...(sample.unknown_rules ?? []),
                  ].join(", ") || sample.status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

function RulesPage() {
  const isAdmin = useIsOrgAdmin()
  const catalogue = useRuleCatalogue()
  const ruleSet = useRuleSet()
  const versions = useRuleSetVersions()
  const save = useSaveRuleSet()
  const activate = useActivateVersion()
  const preview = usePreviewRules()

  const [draft, setDraft] = React.useState<RuleDefinition[] | null>(null)
  // Adopt the saved rules the first time they arrive, and after each save.
  const saved = ruleSet.data?.definition?.rules
  const [syncedVersion, setSyncedVersion] = React.useState<number | null>(null)
  if (ruleSet.data && ruleSet.data.version_number !== syncedVersion) {
    setSyncedVersion(ruleSet.data.version_number)
    setDraft((saved ?? []).map((rule) => ({ ...rule })))
  }

  const rules = draft ?? []
  const dirty =
    draft !== null && JSON.stringify(draft) !== JSON.stringify(saved ?? [])

  function definition() {
    return { schema_version: 1, combinator: "all" as const, rules }
  }

  if (catalogue.isPending || ruleSet.isPending) {
    return (
      <>
        <PageHeader title="Bidding criteria" />
        <Skeleton className="h-64 w-full" />
      </>
    )
  }

  if (catalogue.error || !catalogue.data) {
    return (
      <>
        <PageHeader title="Bidding criteria" />
        <ApiErrorAlert error={catalogue.error} />
      </>
    )
  }

  const presets = catalogue.data.presets ?? []

  return (
    <>
      <PageHeader
        title="Bidding criteria"
        description="Rules that decide whether a tender is one you can actually bid on."
        actions={
          isAdmin ? (
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={preview.isPending || rules.length === 0}
                onClick={() => preview.mutate(definition())}
              >
                {preview.isPending ? (
                  <Spinner data-icon="inline-start" />
                ) : (
                  <PlayIcon data-icon="inline-start" />
                )}
                Try it
              </Button>
              <Button
                disabled={save.isPending || !dirty}
                onClick={() =>
                  save.mutate({
                    name: ruleSet.data?.name ?? "Bidding criteria",
                    definition: definition(),
                    note: null,
                  })
                }
              >
                {save.isPending ? (
                  <Spinner data-icon="inline-start" />
                ) : (
                  <SaveIcon data-icon="inline-start" />
                )}
                Save
              </Button>
            </div>
          ) : undefined
        }
      />

      <PageBody>
        <PageSection
          title="Rules"
          caption={
            'All rules must be met. A rule marked "blocks bidding" can make a tender ineligible; an advisory one only colours the recommendation.'
          }
        >
          <div className="flex flex-col gap-4">
            {rules.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No criteria yet — every tender counts as eligible.
              </p>
            ) : (
              <ul className="flex flex-col gap-3">
                {rules.map((rule, index) => (
                  <RuleRow
                    key={rule.id}
                    rule={rule}
                    catalogue={catalogue.data}
                    onChange={(next) =>
                      setDraft(rules.map((r, i) => (i === index ? next : r)))
                    }
                    onRemove={() =>
                      setDraft(rules.filter((_, i) => i !== index))
                    }
                  />
                ))}
              </ul>
            )}

            {isAdmin ? (
              <Dialog>
                <DialogTrigger
                  render={
                    <Button variant="outline" className="self-start">
                      <PlusIcon data-icon="inline-start" />
                      Add a rule
                    </Button>
                  }
                />
                <DialogContent className="max-w-lg">
                  <DialogHeader>
                    <DialogTitle>Add a rule</DialogTitle>
                    <DialogDescription>
                      Start from something most companies want, then adjust it.
                    </DialogDescription>
                  </DialogHeader>
                  <ItemGroup className="gap-2">
                    {presets.map((preset) => (
                      <Item
                        key={preset.key}
                        variant="outline"
                        onClick={() =>
                          setDraft([...rules, ruleFromPreset(preset, rules)])
                        }
                      >
                        <ItemContent>
                          <ItemTitle>{preset.label}</ItemTitle>
                          <ItemDescription>
                            {preset.description}
                          </ItemDescription>
                        </ItemContent>
                      </Item>
                    ))}
                  </ItemGroup>
                </DialogContent>
              </Dialog>
            ) : null}

            <ApiErrorAlert error={save.error} />
          </div>
        </PageSection>

        {preview.data ? (
          <PageSection
            title="What this would do"
            caption="Run against your open tenders. Nothing is saved until you press Save."
          >
            <PreviewPanel preview={preview} rules={rules} />
          </PageSection>
        ) : null}

        {isAdmin && (versions.data?.length ?? 0) > 1 ? (
          <PageSection
            title="History"
            caption="Older versions are kept, so a past verdict can always be explained."
          >
            <ul className="flex flex-col gap-2">
              {(versions.data ?? []).map((version) => (
                <li
                  key={version.id}
                  className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
                >
                  <span className="text-sm">
                    Version {version.version_number}
                    {version.note ? ` — ${version.note}` : ""}
                  </span>
                  {version.version_number === ruleSet.data?.version_number ? (
                    <Badge variant="secondary">Active</Badge>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={activate.isPending}
                      onClick={() => activate.mutate(version.id)}
                    >
                      <RotateCcwIcon data-icon="inline-start" />
                      Restore
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </PageSection>
        ) : null}
      </PageBody>
    </>
  )
}
