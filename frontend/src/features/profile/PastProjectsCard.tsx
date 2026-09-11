import { PlusIcon, XIcon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { PageSection } from "@/components/layout/PageSection"
import { CountryCombobox } from "@/components/form/CountryCombobox"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { FieldGroup } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import {
  useAddProject,
  useDeleteProject,
  useTaxonomies,
  type PastProject,
  type PastProjectIn,
  type Profile,
  type Sector,
} from "@/features/profile/api"
import { formatDate, formatValue } from "@/features/tenders/format"
import { countryName } from "@/lib/data/locale"
import { RhfField } from "@/lib/forms/RhfField"
import { useZodForm } from "@/lib/forms/useZodForm"

/** Base UI's Select needs a real value for "nothing chosen"; null is not one. */
const NO_SECTOR = "__none__"

const schema = z
  .object({
    title: z.string().trim().min(1, "A title is required").max(300),
    client: z.string().trim().max(300).optional(),
    description: z.string().trim().max(4000).optional(),
    sector: z.string().optional(),
    country: z.string().trim().optional(),
    value: z.string().optional(),
    currency: z.string().trim().max(3).optional(),
    started_on: z.string().optional(),
    completed_on: z.string().optional(),
  })
  .refine((v) => !v.value?.trim() || Number(v.value) >= 0, {
    path: ["value"],
    message: "Enter an amount of zero or more",
  })
  .refine(
    (v) => !v.started_on || !v.completed_on || v.completed_on >= v.started_on,
    { path: ["completed_on"], message: "Completion cannot precede the start" }
  )

/** "" ⇄ null — the form edits text, the API stores nulls. */
function orNull(value: string | undefined): string | null {
  const trimmed = value?.trim()
  return trimmed ? trimmed : null
}

function AddProjectDialog({ profile }: { profile: Profile }) {
  const [open, setOpen] = React.useState(false)
  const add = useAddProject()
  const taxonomies = useTaxonomies()

  const sectors = [
    { value: NO_SECTOR, label: "Not specified" },
    ...(taxonomies.data?.sectors ?? []).map((s) => ({
      value: s.value,
      label: s.label,
    })),
  ]

  const form = useZodForm({
    schema,
    defaultValues: {
      title: "",
      client: "",
      description: "",
      sector: NO_SECTOR,
      country: "",
      value: "",
      // Most firms quote every contract in the currency they report turnover in.
      currency: profile.turnover_currency ?? "",
      started_on: "",
      completed_on: "",
    },
  })

  const onSubmit = form.handleSubmit(async (values) => {
    const amount = values.value?.trim()
    const body: PastProjectIn = {
      title: values.title,
      client: orNull(values.client),
      description: orNull(values.description),
      sector:
        values.sector && values.sector !== NO_SECTOR
          ? (values.sector as Sector)
          : null,
      country: orNull(values.country)?.toUpperCase() ?? null,
      value: amount ? Number(amount) : null,
      currency: orNull(values.currency)?.toUpperCase() ?? null,
      started_on: orNull(values.started_on),
      completed_on: orNull(values.completed_on),
    }
    await add.mutateAsync(body)
    form.reset()
    setOpen(false)
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={<Button variant="outline" className="self-start" />}
      >
        <PlusIcon data-icon="inline-start" />
        Add project
      </DialogTrigger>
      <DialogContent className="max-h-[85svh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
          <DialogHeader>
            <DialogTitle>Add a past project</DialogTitle>
            <DialogDescription>
              Only the title is required. Everything else sharpens the match.
            </DialogDescription>
          </DialogHeader>

          <FieldGroup>
            <RhfField
              form={form}
              name="title"
              label="What the contract was"
              description="Write it the way the work would be advertised."
            >
              <Input placeholder="Core network upgrade for a district hospital" />
            </RhfField>

            <RhfField form={form} name="client" label="Client">
              <Input placeholder="Directorate General of Health Services" />
            </RhfField>

            <RhfField
              form={form}
              name="description"
              label="Scope"
              description="Compared against the substance of each notice, so prose beats a list of nouns."
            >
              <Textarea
                rows={3}
                placeholder="Supply, installation and three-year support of switching, routing and a redundant core…"
              />
            </RhfField>

            <div className="grid gap-5 sm:grid-cols-2">
              <RhfField form={form} name="sector" label="Sector">
                {(control) => (
                  <Select
                    items={sectors}
                    value={(control.value as string) || NO_SECTOR}
                    onValueChange={(next: string | null) =>
                      control.onChange(next ?? NO_SECTOR)
                    }
                  >
                    <SelectTrigger
                      id={control.id}
                      className="w-full"
                      aria-invalid={control["aria-invalid"]}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {sectors.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                )}
              </RhfField>

              <RhfField form={form} name="country" label="Country">
                {(control) => (
                  <CountryCombobox
                    id={control.id}
                    name={control.name}
                    value={(control.value as string) ?? ""}
                    onValueChange={control.onChange}
                    onBlur={control.onBlur}
                    aria-invalid={control["aria-invalid"]}
                    aria-describedby={control["aria-describedby"]}
                  />
                )}
              </RhfField>

              <RhfField form={form} name="value" label="Contract value">
                <Input
                  type="number"
                  inputMode="decimal"
                  placeholder="45000000"
                />
              </RhfField>

              <RhfField form={form} name="currency" label="Currency">
                <Input placeholder="BDT" maxLength={3} />
              </RhfField>

              <RhfField form={form} name="started_on" label="Started">
                <Input type="date" />
              </RhfField>

              <RhfField form={form} name="completed_on" label="Completed">
                <Input type="date" />
              </RhfField>
            </div>
          </FieldGroup>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={add.isPending}>
              {add.isPending ? <Spinner data-icon="inline-start" /> : null}
              Add project
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * A stored sector as a human reads it. The value is a database enum — `it`,
 * `public_works` — and printing it raw drops a column name into a line of
 * otherwise typeset text. Matches how the taxonomies endpoint labels them.
 */
function sectorLabel(value: string | null | undefined): string | null {
  if (!value) return null
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ")
}

/** The one line under a title: everything recorded, nothing empty. */
function summary(project: PastProject): string {
  const period = [project.started_on, project.completed_on].some(Boolean)
    ? `${formatDate(project.started_on)} – ${formatDate(project.completed_on)}`
    : null

  return [
    project.client,
    sectorLabel(project.sector),
    countryName(project.country) || null,
    period,
    project.value != null ? formatValue(project.value, project.currency) : null,
  ]
    .filter(Boolean)
    .join(" · ")
}

export function PastProjectsCard({ profile }: { profile: Profile }) {
  const remove = useDeleteProject()
  const projects = profile.past_projects ?? []

  return (
    <PageSection
      title="Past projects"
      caption="Evidence of delivery. Each project is matched on its own, and rules that demand a number of comparable contracts count these."
    >
      <div className="flex flex-col gap-4">
        <AddProjectDialog profile={profile} />

        {projects.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing recorded yet, so a tender asking for comparable work cannot
            see any.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {projects.map((project) => (
              <li
                key={project.id}
                className="flex items-start justify-between gap-2 rounded-md border px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-sm">{project.title}</p>
                  {summary(project) ? (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {summary(project)}
                    </p>
                  ) : null}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${project.title}`}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(project)}
                >
                  <XIcon />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </PageSection>
  )
}
