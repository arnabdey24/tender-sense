import { createFileRoute } from "@tanstack/react-router"
import { PlusIcon, RefreshCwIcon, SaveIcon, XIcon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { PageHeader } from "@/components/layout/PageHeader"
import { PageBody, PageSection } from "@/components/layout/PageSection"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { FieldGroup } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { AutoSetup } from "@/features/aiassist/AutoSetup"
import { ImproveButton } from "@/features/aiassist/ImproveButton"
import type { CompanyResearch } from "@/features/aiassist/api"
import { takeProfileDraft } from "@/features/aiassist/draft"
import { useCurrentOrg } from "@/features/org/api"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { PastProjectsCard } from "@/features/profile/PastProjectsCard"
import {
  useAddCertification,
  useAddService,
  useCompleteness,
  useDeleteCertification,
  useDeleteService,
  useProfile,
  useRematch,
  useTaxonomies,
  useUpdateProfile,
  type Profile,
  type ProfileUpdate,
} from "@/features/profile/api"
import { RhfField } from "@/lib/forms/RhfField"
import { useZodForm } from "@/lib/forms/useZodForm"
import { useIsOrgAdmin } from "@/lib/auth/store"

export const Route = createFileRoute("/_app/app/settings/profile")({
  component: ProfilePage,
})

const schema = z.object({
  overview: z.string().trim().max(8000).optional(),
  sectors: z.string().optional(),
  geographies: z.string().optional(),
  keywords: z.string().optional(),
  annual_turnover: z.string().optional(),
  turnover_currency: z.string().trim().max(3).optional(),
})

/** "a, b , c" ⇄ ["a","b","c"] — the form edits text, the API takes lists. */
function toList(value: string | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
}

function CapabilityForm({ profile }: { profile: Profile }) {
  const update = useUpdateProfile()
  const taxonomies = useTaxonomies()
  const organization = useCurrentOrg()

  const form = useZodForm({
    schema,
    defaultValues: {
      overview: profile.overview ?? "",
      sectors: (profile.sectors ?? []).join(", "),
      geographies: (profile.geographies ?? []).join(", "),
      keywords: (profile.keywords ?? []).join(", "),
      annual_turnover: profile.annual_turnover?.toString() ?? "",
      turnover_currency: profile.turnover_currency ?? "",
    },
  })

  const known = new Set((taxonomies.data?.sectors ?? []).map((s) => s.value))
  const overview = form.watch("overview")

  /**
   * Fill the empty fields from a website reading, leave the rest alone.
   *
   * Sectors are intersected with what the matcher understands before they go
   * in, for the same reason the save path filters them: a sector the scorer
   * has never heard of is dropped silently on submit, and showing it in the
   * box first would promise something the save then quietly removes.
   */
  const applyDraft = React.useCallback(
    (draft: CompanyResearch) => {
      const fill = (
        field: "overview" | "sectors" | "geographies" | "keywords",
        value: string
      ) => {
        if (!value) return
        if ((form.getValues(field) ?? "").trim()) return
        form.setValue(field, value, { shouldDirty: true })
      }
      const sectors = (draft.sectors ?? []).filter((s) =>
        known.size ? known.has(s) : true
      )
      fill("overview", draft.overview ?? "")
      fill("sectors", sectors.join(", "))
      fill("geographies", (draft.geographies ?? []).join(", "))
      fill("keywords", (draft.keywords ?? []).join(", "))
    },
    // `known` is rebuilt each render from a query with `staleTime: Infinity`,
    // so keying on its size is stable and avoids a new callback per keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [form, known.size]
  )

  /*
    Pick up the half of the onboarding reading that had nowhere to go at the
    time. Runs once, and only into fields that are still empty, so it can
    never overwrite something typed since.
  */
  React.useEffect(() => {
    const carried = takeProfileDraft()
    if (carried) applyDraft(carried)
  }, [applyDraft])

  const onSubmit = form.handleSubmit(async (values) => {
    const turnover = values.annual_turnover?.trim()
    await update.mutateAsync({
      overview: values.overview || null,
      // Only sectors the matcher understands; anything else is dropped rather
      // than sent and rejected.
      sectors: toList(values.sectors).filter((s) =>
        known.size ? known.has(s) : true
      ) as NonNullable<ProfileUpdate["sectors"]>,
      geographies: toList(values.geographies),
      keywords: toList(values.keywords),
      annual_turnover: turnover ? Number(turnover) : null,
      turnover_currency: values.turnover_currency || null,
    })
    form.reset(values)
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      <FieldGroup>
        {/* The one press of Auto setup that onboarding offered is often long
            past by the time anyone opens this page, and the organization's
            website is already on file — so the button is here too, with the
            address it should read already known. */}
        <AutoSetup
          url={organization.data?.website ?? ""}
          onDraft={applyDraft}
          label="Auto setup from your website"
          hint={
            organization.data?.website
              ? `We read ${organization.data.website} and fill in the empty fields below. Nothing is saved until you press save.`
              : "Add your website under Settings → Organization and this can fill the form in for you."
          }
        />

        <RhfField
          form={form}
          name="overview"
          label="What your company does"
          description="The single biggest influence on which tenders you are shown."
          below={
            <ImproveButton
              field="overview"
              value={overview ?? ""}
              onChange={(next) =>
                form.setValue("overview", next, { shouldDirty: true })
              }
            />
          }
        >
          <Textarea
            rows={4}
            placeholder="Systems integration, enterprise networking and data centre build-out for public sector clients…"
          />
        </RhfField>

        <RhfField
          form={form}
          name="sectors"
          label="Sectors"
          description={
            taxonomies.data
              ? `Comma separated. Known: ${taxonomies.data.sectors
                  .map((s) => s.value)
                  .join(", ")}`
              : "Comma separated."
          }
        >
          <Input placeholder="it, telecom" />
        </RhfField>

        <RhfField
          form={form}
          name="geographies"
          label="Where you bid"
          description="Comma-separated ISO country codes, e.g. BD, NP."
        >
          <Input placeholder="BD, NP" />
        </RhfField>

        <RhfField
          form={form}
          name="keywords"
          label="Keywords"
          description="Terms you use about yourselves. Comma separated."
        >
          <Input placeholder="networking, data centre" />
        </RhfField>

        <RhfField form={form} name="annual_turnover" label="Annual turnover">
          <Input type="number" inputMode="decimal" placeholder="200000000" />
        </RhfField>

        <RhfField form={form} name="turnover_currency" label="Currency">
          <Input placeholder="BDT" maxLength={3} />
        </RhfField>
      </FieldGroup>

      <Button
        type="submit"
        className="self-start"
        disabled={update.isPending || !form.formState.isDirty}
      >
        {update.isPending ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <SaveIcon data-icon="inline-start" />
        )}
        Save capabilities
      </Button>
    </form>
  )
}

/**
 * Suggestions here matter more than they do on certifications, not less.
 *
 * A certification is checked by a rule that canonicalises what it is given, so
 * a typo mostly survives. A service is *embedded* and every grade on the site
 * is scored against it — "netwrk integration" becomes a facet that resembles
 * nothing, silently dragging the profile's matches down with no error to read.
 * The field that feeds the matcher was the one field with nothing to pick from.
 */
function ServicesCard({ profile }: { profile: Profile }) {
  const add = useAddService()
  const remove = useDeleteService()
  const taxonomies = useTaxonomies()
  const [name, setName] = React.useState("")

  // Do not re-offer what is already on the list.
  const taken = new Set(
    (profile.services ?? []).map((s) => s.name.trim().toLowerCase())
  )
  const suggestions = (taxonomies.data?.common_services ?? []).filter(
    (item) => !taken.has(item.toLowerCase())
  )

  return (
    <PageSection
      title="Services"
      caption="Each service is matched separately, so a tender only has to fit one of them. Unlike certifications, the wording is read by the matcher — pick a suggestion where one fits."
    >
      <div className="flex flex-col gap-4">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            const trimmed = name.trim()
            if (!trimmed) return
            add.mutate(
              { name: trimmed, position: profile.services?.length ?? 0 },
              { onSuccess: () => setName("") }
            )
          }}
        >
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Network integration"
            aria-label="Service name"
            list="common-services"
          />
          <datalist id="common-services">
            {suggestions.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
          <Button type="submit" disabled={add.isPending}>
            <PlusIcon data-icon="inline-start" />
            Add
          </Button>
        </form>

        {(profile.services ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">No services yet.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {(profile.services ?? []).map((service) => (
              <li
                key={service.id}
                className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
              >
                <span className="text-sm">{service.name}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${service.name}`}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(service)}
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

function CertificationsCard({ profile }: { profile: Profile }) {
  const add = useAddCertification()
  const remove = useDeleteCertification()
  const taxonomies = useTaxonomies()
  const [label, setLabel] = React.useState("")

  return (
    <PageSection
      title="Certifications"
      caption="Used by eligibility rules. Spelling and punctuation do not matter."
    >
      <div className="flex flex-col gap-4">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            const trimmed = label.trim()
            if (!trimmed) return
            add.mutate({ label: trimmed }, { onSuccess: () => setLabel("") })
          }}
        >
          <Input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="ISO 9001"
            aria-label="Certification"
            list="common-certifications"
          />
          <datalist id="common-certifications">
            {(taxonomies.data?.common_certifications ?? []).map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
          <Button type="submit" disabled={add.isPending}>
            <PlusIcon data-icon="inline-start" />
            Add
          </Button>
        </form>

        <div className="flex flex-wrap gap-2">
          {(profile.certifications ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">None recorded.</p>
          ) : (
            (profile.certifications ?? []).map((certification) => (
              <Badge
                key={certification.id}
                variant="secondary"
                className="gap-1"
              >
                {certification.label}
                <button
                  type="button"
                  aria-label={`Remove ${certification.label}`}
                  onClick={() => remove.mutate(certification)}
                  className="hover:text-destructive"
                >
                  <XIcon className="size-3" />
                </button>
              </Badge>
            ))
          )}
        </div>
      </div>
    </PageSection>
  )
}

function ProfilePage() {
  const isAdmin = useIsOrgAdmin()
  const profile = useProfile()
  const completeness = useCompleteness()
  const rematch = useRematch()

  if (profile.isPending) {
    return (
      <>
        <PageHeader title="Capability profile" />
        <Skeleton className="h-72 w-full" />
      </>
    )
  }

  if (profile.error || !profile.data) {
    return (
      <>
        <PageHeader title="Capability profile" />
        <ApiErrorAlert error={profile.error} />
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Capability profile"
        description="What your company does. This is what tenders are matched against."
        actions={
          isAdmin ? (
            <Button
              variant="outline"
              disabled={rematch.isPending}
              onClick={() => rematch.mutate()}
            >
              <RefreshCwIcon data-icon="inline-start" />
              Re-score now
            </Button>
          ) : undefined
        }
      />

      <PageBody>
        <PageSection
          title="Completeness"
          caption={completeness.data?.next_step ?? "Your profile is complete."}
        >
          <div className="flex flex-col gap-3">
            <Progress
              value={completeness.data?.score ?? 0}
              aria-label="Profile completeness"
            />
            <div className="flex flex-wrap gap-2">
              {(completeness.data?.sections ?? []).map((section) => (
                <Badge
                  key={section.key}
                  variant={section.complete ? "success" : "outline"}
                >
                  {section.label}
                </Badge>
              ))}
            </div>
          </div>
        </PageSection>

        <PageSection
          title="Capabilities"
          caption={
            isAdmin
              ? "Saving re-scores every open tender against the new profile."
              : "Ask an admin to change these."
          }
        >
          {isAdmin ? (
            <CapabilityForm key={profile.data.version} profile={profile.data} />
          ) : (
            <p className="text-sm whitespace-pre-wrap">
              {profile.data.overview || "No overview yet."}
            </p>
          )}
        </PageSection>

        {isAdmin ? (
          <>
            <ServicesCard profile={profile.data} />
            <PastProjectsCard profile={profile.data} />
            <CertificationsCard profile={profile.data} />
          </>
        ) : null}
      </PageBody>
    </>
  )
}
