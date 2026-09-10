import { createFileRoute, Link } from "@tanstack/react-router"
import {
  ArrowRightIcon,
  CheckCircle2Icon,
  HelpCircleIcon,
} from "lucide-react"

import { Logo } from "@/components/brand/Logo"
import { ThemeToggle } from "@/components/layout/ThemeToggle"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

export const Route = createFileRoute("/")({
  component: LandingPage,
})

/**
 * One illustrative assessment, shown at the scale the product actually matters
 * at. It is synthetic — there are no real customers to quote — and the page
 * says so beneath it rather than implying a case study.
 */
const SAMPLE = {
  grade: "A",
  recommendation: "Bid",
  title: "Construction of RCC road and surface drain, Package WD-07",
  entity: "Local Government Engineering Department, Rangpur",
  reference: "e-GP · 1047821",
  closesIn: "6 days",
  facts: [
    { label: "Estimated value", value: "৳ 4,20,00,000" },
    { label: "Procurement method", value: "Open Tendering (OTM)" },
    { label: "Published", value: "3 days ago" },
    { label: "Similarity", value: "0.74" },
  ],
  rules: [
    {
      status: "met" as const,
      requirement: "Minimum annual turnover ৳ 3,00,00,000",
      detail: "Your recorded turnover is ৳ 5,10,00,000",
    },
    {
      status: "met" as const,
      requirement: "ISO 9001 certification",
      detail: "On file, valid to March 2027",
    },
    {
      status: "check" as const,
      requirement: "Three similar works in the last five years",
      detail: "The notice does not state a threshold — worth confirming",
    },
  ],
}

/**
 * The order is the product: a notice is only worth grading once it has been
 * read, and only worth alerting on once the rules have run. The numbers carry
 * that sequence rather than decorating the section.
 */
const PIPELINE = [
  {
    title: "It reads the portals",
    body: "e-GP Bangladesh and the World Bank procurement feed, polled for new notices and re-read when one is corrected. English, Bangla, or a mix of both.",
  },
  {
    title: "It matches on meaning",
    body: "Your services, past projects, sectors and geographies are compared against the substance of each notice — not a keyword list. A road-maintenance tender still reaches a firm that wrote “highway rehabilitation”.",
  },
  {
    title: "It applies your rules",
    body: "Minimum turnover, required certifications, years of experience, joint-venture terms. Your thresholds, evaluated the same way every time, with BDT and USD compared through recorded rates.",
  },
  {
    title: "It grades, and shows its work",
    body: "Every grade opens onto the quoted line it came from, which rule passed or failed, and which version of your profile produced it. Where the notice is silent, it says so.",
  },
  {
    title: "It tells you in time",
    body: "A ranked digest each morning at your hour, an instant alert when a strong fit is also eligible, and reminders as the deadline approaches on anything you marked to bid.",
  },
] as const

const GRADES = [
  {
    grade: "S",
    variant: "gradeS",
    verdict: "Bid",
    threshold: "0.78 +",
    note: "Close to everything you have done before.",
  },
  {
    grade: "A",
    variant: "gradeA",
    verdict: "Bid",
    threshold: "0.70 +",
    note: "Clearly within your capability.",
  },
  {
    grade: "B",
    variant: "gradeB",
    verdict: "Hold",
    threshold: "0.62 +",
    note: "Plausible, but read it before committing.",
  },
  {
    grade: "C",
    variant: "gradeC",
    verdict: "Skip",
    threshold: "under 0.62",
    note: "Far enough away that it is not worth the week.",
  },
] as const

/** The product's real output, at the size it deserves. */
function AssessmentCard() {
  return (
    <figure className="m-0">
      <div className="overflow-hidden rounded-2xl bg-card ring-1 shadow-xl ring-foreground/10">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b px-6 py-4">
          <Badge variant="gradeA" className="h-6 w-7 justify-center text-sm">
            {SAMPLE.grade}
          </Badge>
          <span className="text-sm font-medium">{SAMPLE.recommendation}</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-sm text-muted-foreground">Eligible</span>
          <span className="ml-auto text-sm font-medium text-warning tabular-nums">
            Closes in {SAMPLE.closesIn}
          </span>
        </div>

        <div className="px-6 py-5">
          <h2 className="text-pretty text-lg leading-snug font-medium">
            {SAMPLE.title}
          </h2>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {SAMPLE.entity}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground tabular-nums">
            {SAMPLE.reference}
          </p>
        </div>

        <dl className="grid grid-cols-2 border-t sm:grid-cols-4">
          {SAMPLE.facts.map((fact) => (
            <div
              key={fact.label}
              className="border-r border-b px-6 py-3 last:border-r-0 sm:border-b-0 sm:px-4 sm:py-4"
            >
              <dt className="text-xs text-muted-foreground">{fact.label}</dt>
              <dd className="mt-1 text-sm font-medium tabular-nums">
                {fact.value}
              </dd>
            </div>
          ))}
        </dl>

        <ul className="flex flex-col border-t">
          {SAMPLE.rules.map((rule) => (
            <li
              key={rule.requirement}
              className="flex gap-3 border-b px-6 py-3.5 last:border-b-0"
            >
              {rule.status === "met" ? (
                <CheckCircle2Icon className="mt-0.5 size-4 shrink-0 text-success" />
              ) : (
                <HelpCircleIcon className="mt-0.5 size-4 shrink-0 text-warning" />
              )}
              <div className="min-w-0">
                <p className="text-sm font-medium">{rule.requirement}</p>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {rule.detail}
                </p>
              </div>
              <span
                className={
                  rule.status === "met"
                    ? "ml-auto shrink-0 self-center text-xs font-medium text-success"
                    : "ml-auto shrink-0 self-center text-xs font-medium text-warning"
                }
              >
                {rule.status === "met" ? "Met" : "Needs checking"}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <figcaption className="mt-3 text-xs text-muted-foreground">
        An illustrative assessment. The notice, the company and the figures are
        synthetic — TenderSense has no customer data to show you.
      </figcaption>
    </figure>
  )
}

function LandingPage() {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="material-chrome sticky top-0 z-20 border-b">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-6 lg:px-10">
          <Logo size={26} />
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <Button
              variant="ghost"
              size="sm"
              render={<Link to="/login" />}
              nativeButton={false}
            >
              Sign in
            </Button>
            <Button
              size="sm"
              render={<Link to="/register" />}
              nativeButton={false}
            >
              Create account
            </Button>
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero: the argument on the left, the product's actual output on the
            right. No centred column, no colour field. */}
        <section className="border-b">
          <div className="mx-auto grid w-full max-w-6xl gap-x-14 gap-y-12 px-6 py-20 lg:grid-cols-12 lg:px-10 lg:py-28">
            <div className="flex flex-col justify-center lg:col-span-5">
              <h1 className="text-balance text-4xl leading-[1.05] font-semibold tracking-[-0.03em] sm:text-5xl">
                Know which tenders are worth bidding, before the day starts.
              </h1>
              <p className="mt-6 text-pretty text-lg leading-relaxed text-muted-foreground">
                TenderSense reads every new public procurement notice, matches it
                against what your company can actually deliver, checks it against
                your own eligibility rules, and grades it — with the evidence
                attached, so you can check the answer rather than trust it.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Button
                  size="lg"
                  render={<Link to="/register" />}
                  nativeButton={false}
                >
                  Create account
                  <ArrowRightIcon data-icon="inline-end" />
                </Button>
                <Button
                  size="lg"
                  variant="outline"
                  render={<Link to="/login" />}
                  nativeButton={false}
                >
                  Sign in
                </Button>
              </div>
              <p className="mt-6 text-sm text-muted-foreground">
                Covers e-GP Bangladesh and the World Bank procurement feed.
              </p>
            </div>

            <div className="lg:col-span-7">
              <AssessmentCard />
            </div>
          </div>
        </section>

        {/* Pipeline: numbers hang in the margin; the rules do the separating. */}
        <section className="border-b">
          <div className="mx-auto w-full max-w-6xl px-6 py-20 lg:px-10 lg:py-24">
            <div className="grid gap-x-14 gap-y-10 lg:grid-cols-12">
              <div className="lg:col-span-4">
                <h2 className="text-balance text-2xl font-semibold tracking-[-0.02em] sm:text-3xl">
                  From published notice to your morning shortlist
                </h2>
                <p className="mt-4 text-pretty text-sm leading-relaxed text-muted-foreground">
                  Five steps run before anything reaches you. Each one is
                  recorded, so a grade can always be traced back through them.
                </p>
              </div>

              <ol className="flex flex-col lg:col-span-8">
                {PIPELINE.map((step, index) => (
                  <li
                    key={step.title}
                    className="grid grid-cols-[2.5rem_1fr] gap-x-5 border-t py-6 first:border-t-0 first:pt-0"
                  >
                    <span
                      aria-hidden
                      className="text-sm leading-6 font-medium text-muted-foreground tabular-nums"
                    >
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <h3 className="text-base leading-6 font-medium">
                        {step.title}
                      </h3>
                      <p className="mt-2 max-w-prose text-pretty text-sm leading-relaxed text-muted-foreground">
                        {step.body}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>

        {/* Grades */}
        <section className="border-b bg-muted/30">
          <div className="mx-auto w-full max-w-6xl px-6 py-20 lg:px-10 lg:py-24">
            <div className="grid gap-x-14 gap-y-10 lg:grid-cols-12">
              <div className="lg:col-span-4">
                <h2 className="text-balance text-2xl font-semibold tracking-[-0.02em] sm:text-3xl">
                  Four grades, and a recommendation you can argue with
                </h2>
                <p className="mt-4 text-pretty text-sm leading-relaxed text-muted-foreground">
                  The grade measures how close the notice sits to your profile.
                  The recommendation weighs that against your eligibility rules —
                  so a perfect match you are not qualified for is still a skip,
                  and it will name the requirement that stopped it.
                </p>
              </div>

              <div className="lg:col-span-8">
                <dl className="flex flex-col">
                  {GRADES.map((row) => (
                    <div
                      key={row.grade}
                      className="grid grid-cols-[2rem_4rem_1fr] items-baseline gap-x-5 border-t py-4 first:border-t-0 sm:grid-cols-[2rem_4rem_6rem_1fr]"
                    >
                      <dt>
                        <Badge
                          variant={row.variant}
                          className="w-7 justify-center"
                        >
                          {row.grade}
                        </Badge>
                      </dt>
                      <dd className="text-sm font-medium">{row.verdict}</dd>
                      <dd className="hidden text-sm text-muted-foreground tabular-nums sm:block">
                        {row.threshold}
                      </dd>
                      <dd className="col-span-3 text-sm text-muted-foreground sm:col-span-1">
                        {row.note}
                      </dd>
                    </div>
                  ))}
                </dl>

                <p className="mt-8 max-w-prose text-pretty text-sm leading-relaxed text-muted-foreground">
                  Where a notice does not state a requirement, the rule returns{" "}
                  <span className="font-medium text-warning">
                    needs checking
                  </span>{" "}
                  rather than a guess. Bidding documents are not parsed yet, so
                  that happens more often than it eventually will — and you are
                  always told which field it was.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Close */}
        <section>
          <div className="mx-auto w-full max-w-6xl px-6 py-20 lg:px-10 lg:py-24">
            <div className="grid items-end gap-x-14 gap-y-8 lg:grid-cols-12">
              <div className="lg:col-span-7">
                <h2 className="text-balance text-2xl font-semibold tracking-[-0.02em] sm:text-3xl">
                  Set up your profile once.
                </h2>
                <p className="mt-4 max-w-prose text-pretty text-muted-foreground">
                  Your capability profile and eligibility rules take an
                  afternoon. After that the shortlist arrives on its own, every
                  morning, at the hour you choose.
                </p>
              </div>
              <div className="lg:col-span-5 lg:justify-self-end">
                <Button
                  size="lg"
                  render={<Link to="/register" />}
                  nativeButton={false}
                >
                  Create account
                  <ArrowRightIcon data-icon="inline-end" />
                </Button>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-start justify-between gap-4 px-6 py-8 sm:flex-row sm:items-center lg:px-10">
          <Logo size={22} />
          <p className="text-xs text-muted-foreground">
            Public procurement intelligence for Bangladesh and the multilateral
            development banks.
          </p>
        </div>
      </footer>
    </div>
  )
}
