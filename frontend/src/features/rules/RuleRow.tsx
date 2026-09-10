import { TrashIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { TenderFilterSelect } from "@/features/tenders/TenderFilterSelect"
import type {
  CatalogueAttribute,
  OnMissing,
  Operator,
  RuleCatalogue,
  RuleDefinition,
  Severity,
} from "@/features/rules/api"

/** How each operator wants its value typed. */
type ValueShape = "scalar" | "list" | "range" | "boolean" | "days"

const ON_MISSING_LABELS: Record<OnMissing, string> = {
  // The wording matters: these are what happens when we *cannot tell*, and a
  // user picking "reject" should understand they are rejecting on absence.
  verify: "Ask me to check",
  pass: "Treat as met",
  fail: "Treat as not met",
}

const SEVERITY_LABELS: Record<Severity, string> = {
  hard: "Blocks bidding",
  soft: "Advisory only",
}

function valueShape(catalogue: RuleCatalogue, operator: Operator): ValueShape {
  const entry = catalogue.operators?.find((o) => o.key === operator)
  return (entry?.value_shape ?? "scalar") as ValueShape
}

/** `{source: "literal", data}` — the shape the API expects. */
function literal(data: unknown) {
  return { source: "literal" as const, data }
}

export function RuleRow({
  rule,
  catalogue,
  onChange,
  onRemove,
}: {
  rule: RuleDefinition
  catalogue: RuleCatalogue
  onChange: (next: RuleDefinition) => void
  onRemove: () => void
}) {
  const attributes = catalogue.attributes ?? []
  const attribute: CatalogueAttribute | undefined = attributes.find(
    (a) => a.key === rule.attribute
  )
  const shape = valueShape(catalogue, rule.operator)
  // Narrow the discriminated union once, rather than re-checking at each use.
  const profileValue = rule.value?.source === "profile" ? rule.value : null
  const literalData = rule.value?.source === "literal" ? rule.value.data : null

  function patch(next: Partial<RuleDefinition>) {
    onChange({ ...rule, ...next })
  }

  function changeAttribute(key: string | undefined) {
    if (!key) return
    const target = attributes.find((a) => a.key === key)
    if (!target) return
    // The current operator may not exist on the new attribute, so fall back to
    // its first allowed one rather than sending a pair the engine rejects.
    const operator = target.operators.includes(rule.operator)
      ? rule.operator
      : target.operators[0]
    patch({
      attribute: key,
      operator,
      value: target.profile_field
        ? { source: "profile", field: target.profile_field }
        : literal(null),
    })
  }

  return (
    <li className="flex flex-col gap-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex min-w-52 flex-1 flex-col gap-1">
          <span className="text-xs font-medium">When</span>
          <TenderFilterSelect
            label="Attribute"
            value={rule.attribute}
            anyLabel="Choose…"
            onChange={changeAttribute}
            options={attributes.map((a) => ({ value: a.key, label: a.label }))}
          />
        </div>

        <div className="flex w-44 flex-col gap-1">
          <span className="text-xs font-medium">Condition</span>
          <TenderFilterSelect
            label="Operator"
            value={rule.operator}
            anyLabel="Choose…"
            onChange={(v) => v && patch({ operator: v as Operator })}
            options={(attribute?.operators ?? []).map((op) => ({
              value: op,
              label:
                catalogue.operators?.find((entry) => entry.key === op)?.label ?? op,
            }))}
          />
        </div>

        <div className="flex min-w-52 flex-1 flex-col gap-1">
          <span className="text-xs font-medium">Value</span>
          {profileValue ? (
            <div className="flex h-8 items-center">
              <Badge variant="secondary">
                from your profile: {profileValue.field.replace(/_/g, " ")}
              </Badge>
            </div>
          ) : shape === "boolean" ? (
            <div className="flex h-8 items-center gap-2">
              <Switch
                checked={literalData === true}
                onCheckedChange={(checked) => patch({ value: literal(checked) })}
              />
              <span className="text-sm">{literalData === true ? "Yes" : "No"}</span>
            </div>
          ) : shape === "range" ? (
            <div className="flex gap-2">
              <Input
                type="number"
                placeholder="Min"
                aria-label="Minimum"
                defaultValue={(literalData as { min?: number })?.min ?? ""}
                onChange={(e) =>
                  patch({
                    value: literal({
                      ...(literalData as object),
                      min: e.target.value ? Number(e.target.value) : null,
                    }),
                  })
                }
              />
              <Input
                type="number"
                placeholder="Max"
                aria-label="Maximum"
                defaultValue={(literalData as { max?: number })?.max ?? ""}
                onChange={(e) =>
                  patch({
                    value: literal({
                      ...(literalData as object),
                      max: e.target.value ? Number(e.target.value) : null,
                    }),
                  })
                }
              />
            </div>
          ) : shape === "days" ? (
            <Input
              type="number"
              placeholder="Days"
              aria-label="Days"
              defaultValue={(literalData as { days_from_now?: number })?.days_from_now ?? ""}
              onChange={(e) =>
                patch({
                  value: literal({
                    days_from_now: e.target.value ? Number(e.target.value) : null,
                  }),
                })
              }
            />
          ) : (
            <Input
              placeholder={shape === "list" ? "Comma separated" : "Value"}
              aria-label="Value"
              defaultValue={
                Array.isArray(literalData)
                  ? literalData.join(", ")
                  : ((literalData as string | number) ?? "")
              }
              onChange={(e) => {
                const raw = e.target.value
                patch({
                  value: literal(
                    shape === "list"
                      ? raw
                          .split(",")
                          .map((item) => item.trim())
                          .filter(Boolean)
                      : raw
                  ),
                })
              }}
            />
          )}
        </div>

        <Button
          variant="ghost"
          size="sm"
          aria-label={`Remove ${attribute?.label ?? rule.attribute}`}
          onClick={onRemove}
        >
          <TrashIcon />
        </Button>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex w-44 flex-col gap-1">
          <span className="text-xs font-medium">Importance</span>
          <TenderFilterSelect
            label="Severity"
            value={rule.severity ?? "hard"}
            anyLabel="Blocks bidding"
            onChange={(v) => patch({ severity: (v ?? "hard") as Severity })}
            options={(Object.keys(SEVERITY_LABELS) as Severity[]).map((key) => ({
              value: key,
              label: SEVERITY_LABELS[key],
            }))}
          />
        </div>
        <div className="flex w-52 flex-col gap-1">
          <span className="text-xs font-medium">If the notice does not say</span>
          <TenderFilterSelect
            label="When unknown"
            value={rule.on_missing ?? "verify"}
            anyLabel="Ask me to check"
            onChange={(v) => patch({ on_missing: (v ?? "verify") as OnMissing })}
            options={(Object.keys(ON_MISSING_LABELS) as OnMissing[]).map((key) => ({
              value: key,
              label: ON_MISSING_LABELS[key],
            }))}
          />
        </div>
        <label className="flex h-8 items-center gap-2 text-sm">
          <Switch
            checked={rule.enabled ?? true}
            onCheckedChange={(checked) => patch({ enabled: checked })}
          />
          Active
        </label>
        {attribute ? (
          <span className="text-xs text-muted-foreground">
            {attribute.source === "ai_extraction"
              ? "Read from the notice by AI — low confidence becomes a check."
              : "Taken from the portal."}
          </span>
        ) : null}
      </div>
    </li>
  )
}
