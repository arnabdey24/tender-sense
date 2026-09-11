import { createFileRoute, Link } from "@tanstack/react-router"
import {
  ArrowRightIcon,
  CheckCircle2Icon,
  HelpCircleIcon,
  QuoteIcon,
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
  /**
   * The line the turnover rule was decided against, in the script the notice
   * was published in. Notices arrive in Bangla, English or a mix of the two,
   * and the product reads them where they are — a capability a Bangladeshi
   * bidder has every reason to want proof of before trusting a grade.
   */
  evidence: {
    quote:
      "দরপত্রদাতার বিগত তিন বছরের গড় বার্ষিক টার্নওভার ন্যূনতম ৩,০০,০০,০০০ টাকা হইতে হইবে।",
    gloss:
      "Average annual turnover over the last three years must be at least ৳ 3,00,00,000.",
    field: "Qualification requirements, clause 12(b)",
  },
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

/**
 * The argument the page was missing.
 *
 * Both alternatives are real things a firm evaluates this against, and the
 * distinction is the product's recorded positioning rather than a claim
 * invented for a marketing page: a keyword service has no model of the
 * company, and a fluent summary is not an audit trail. Stated as what each
 * kind of tool can and cannot answer, so a reader can check it rather than
 * take it — which is the same standard the product holds itself to.
 */
const ALTERNATIVES: {
  name: string
  answers: string
  cannot: string
  /** TenderSense's own column. Marked by ink weight, never by a tinted card. */
  own?: boolean
}[] = [
  {
    name: "A keyword alert",
    answers: "Whether a notice contains the words you registered.",
    cannot:
      "Tell you that your turnover is below the floor, or that the wording moved and your term no longer matches.",
  },
  {
    name: "A general-purpose assistant",
    answers: "A fluent summary of whatever you paste into it.",
    cannot:
      "Show which rule failed, against which line of the notice, under which version of your profile — or give the same answer twice.",
  },
  {
    name: "TenderSense",
    answers:
      "A grade, a recommendation, and the evidence for both: the quoted line, the rule result, the profile version.",
    cannot:
      "Read the bidding documents. Where a requirement appears only in an attachment, the rule returns unknown rather than a guess.",
    own: true,
  },
]

/**
 * The shortlist as it actually arrives, which teaches the grading vocabulary
 * better than defining it. The thresholds ride along as annotation; the
 * artifact is the point.
 */
const SHORTLIST = [
  {
    grade: "S",
    variant: "gradeS",
    verdict: "Bid",
    threshold: "0.78 +",
    title: "Supply and installation of network infrastructure, 14 upazila offices",
    entity: "Bangladesh Computer Council",
    closes: "11 days",
    note: "Close to everything you have done before.",
  },
  {
    grade: "A",
    variant: "gradeA",
    verdict: "Bid",
    threshold: "0.70 +",
    title: "Construction of RCC road and surface drain, Package WD-07",
    entity: "LGED, Rangpur",
    closes: "6 days",
    note: "Clearly within your capability.",
  },
  {
    grade: "B",
    variant: "gradeB",
    verdict: "Hold",
    threshold: "0.62 +",
    title: "Periodic maintenance of rural roads, Zone 3",
    entity: "Roads and Highways Department",
    closes: "19 days",
    note: "Plausible, but read it before committing.",
  },
  {
    grade: "C",
    variant: "gradeC",
    verdict: "Skip",
    threshold: "under 0.62",
    title: "Procurement of laboratory reagents and consumables",
    entity: "Directorate General of Health Services",
    closes: "8 days",
    note: "Far enough away that it is not worth the week.",
  },
] as const

/** The product's real output, at the size it deserves. */
function AssessmentCard() {
  return (
    <figure className="m-0">
      <div className="overflow-hidden rounded-2xl bg-card ring-1 shadow-xl ring-foreground/10">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b px-5 py-4 sm:px-6">
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

        <div className="px-5 py-5 sm:px-6">
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
              className="border-r border-b px-5 py-3 last:border-r-0 sm:border-b-0 sm:px-4 sm:py-4"
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
              className="flex flex-wrap gap-x-3 gap-y-1 border-b px-5 py-3.5 last:border-b-0 sm:px-6"
            >
              {rule.status === "met" ? (
                <CheckCircle2Icon className="mt-0.5 size-4 shrink-0 text-success" />
              ) : (
                <HelpCircleIcon className="mt-0.5 size-4 shrink-0 text-warning" />
              )}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{rule.requirement}</p>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {rule.detail}
                </p>
              </div>
              <span
                className={
                  rule.status === "met"
                    ? "shrink-0 self-center text-xs font-medium text-success"
                    : "shrink-0 self-center text-xs font-medium text-warning"
                }
              >
                {rule.status === "met" ? "Met" : "Needs checking"}
              </span>
            </li>
          ))}
        </ul>

        {/*
          The evidence itself, in the script it was published in. A grade with
          no quoted line behind it is the thing this product exists not to be,
          so the card that argues for it has to carry one.
        */}
        <figure className="m-0 border-t bg-muted/40 px-5 py-4 sm:px-6">
          <div className="flex gap-3">
            <QuoteIcon
              aria-hidden
              className="mt-1 size-4 shrink-0 text-muted-foreground"
            />
            <div className="min-w-0">
              <blockquote
                lang="bn"
                className="text-sm leading-[1.7] text-foreground"
              >
                {SAMPLE.evidence.quote}
              </blockquote>
              <p className="mt-1.5 text-sm text-muted-foreground">
                {SAMPLE.evidence.gloss}
              </p>
              <figcaption className="mt-1.5 text-xs text-muted-foreground">
                The line behind the turnover rule — {SAMPLE.evidence.field}
              </figcaption>
            </div>
          </div>
        </figure>
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
            {/*
              Two buttons, a theme control and the mark do not fit in 390px,
              and the page scrolled sideways because of it. The primary action
              is a screen-height below in the hero, so on a phone the header
              carries the way back in and nothing else.
            */}
            <Button
              size="sm"
              className="hidden sm:inline-flex"
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

        {/*
          The distinction, drawn as three answers to the same question rather
          than a feature table with ticks. Columns, not cards: the comparison is
          the structure, and boxing each one would make three objects out of one
          argument.
        */}
        <section className="border-b">
          <div className="mx-auto w-full max-w-6xl px-6 py-20 lg:px-10 lg:py-24">
            <h2 className="max-w-2xl text-balance text-2xl font-semibold tracking-[-0.02em] sm:text-3xl">
              A keyword alert cannot tell you that you are not qualified
            </h2>
            <p className="mt-4 max-w-prose text-pretty text-sm leading-relaxed text-muted-foreground">
              Three kinds of tool answer three different questions. Only one of
              them answers the one a bid manager actually has, which is whether
              this notice is worth two weeks of preparation.
            </p>

            {/*
              Subgrid, because a comparison is read across as much as down: with
              each column laying out independently the second label landed at
              three different heights, and "cannot tell you" stopped being one
              row of the argument. Without subgrid support the columns simply
              stack, which is what they do on a phone anyway.
            */}
            <div className="mt-12 grid gap-x-10 gap-y-8 border-t pt-8 sm:grid-cols-3 sm:grid-rows-[auto_auto_1fr_auto_1fr]">
              {ALTERNATIVES.map((item) => (
                <div
                  key={item.name}
                  className="flex flex-col gap-3 border-t pt-6 first:border-t-0 first:pt-0 sm:row-span-5 sm:grid sm:grid-rows-subgrid sm:gap-0 sm:border-t-0 sm:pt-0"
                >
                  {/*
                    The product's own column is marked by ink weight, not by a
                    tinted card or a coloured border — brand blue is for action,
                    and a highlighted pricing-table column is the tell of a page
                    that needs one.
                  */}
                  <h3
                    className={
                      item.own
                        ? "text-base font-semibold"
                        : "text-base font-medium text-muted-foreground"
                    }
                  >
                    {item.name}
                  </h3>
                  <p className="text-xs font-medium text-muted-foreground sm:pt-4">
                    Answers
                  </p>
                  <p
                    className={
                      item.own
                        ? "text-pretty text-sm leading-relaxed sm:pt-1"
                        : "text-pretty text-sm leading-relaxed text-muted-foreground sm:pt-1"
                    }
                  >
                    {item.answers}
                  </p>
                  <p className="text-xs font-medium text-muted-foreground sm:pt-4">
                    {item.own ? "Does not do yet" : "Cannot tell you"}
                  </p>
                  <p className="text-pretty text-sm leading-relaxed text-muted-foreground sm:pt-1">
                    {item.cannot}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Pipeline: the sequence drawn as a spine, because the order is the
            argument — a notice is only worth grading once it has been read. */}
        <section className="border-b bg-muted/30">
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

              <ol className="relative flex flex-col lg:col-span-8">
                {PIPELINE.map((step, index) => (
                  <li
                    key={step.title}
                    className="relative grid grid-cols-[1.75rem_1fr] gap-x-5 pb-8 last:pb-0 sm:grid-cols-[2.25rem_1fr]"
                  >
                    {/* The rule connects one step to the next, so the sequence
                        is visible rather than merely numbered. It stops at the
                        last step rather than trailing into nothing. */}
                    {index < PIPELINE.length - 1 && (
                      <span
                        aria-hidden
                        className="absolute top-7 bottom-1 left-[0.6875rem] w-px bg-border sm:left-[0.9375rem]"
                      />
                    )}
                    <span
                      aria-hidden
                      className="relative z-10 flex size-6 items-center justify-center rounded-full bg-background text-xs font-medium text-muted-foreground ring-1 ring-border tabular-nums sm:size-8 sm:text-sm"
                    >
                      {index + 1}
                    </span>
                    <div className="pt-0.5 sm:pt-1">
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

        {/*
          Grades, shown as the shortlist they arrive in rather than defined in a
          glossary. The vocabulary is learned from the artifact, which is also
          the only honest way to show what a morning actually looks like.
        */}
        <section className="border-b">
          <div className="mx-auto w-full max-w-6xl px-6 py-20 lg:px-10 lg:py-24">
            <div className="max-w-2xl">
              <h2 className="text-balance text-2xl font-semibold tracking-[-0.02em] sm:text-3xl">
                Four grades, and a recommendation you can argue with
              </h2>
              <p className="mt-4 text-pretty text-sm leading-relaxed text-muted-foreground">
                The grade measures how close the notice sits to your profile. The
                recommendation weighs that against your eligibility rules — so a
                perfect match you are not qualified for is still a skip, and it
                will name the requirement that stopped it.
              </p>
            </div>

            <ul className="mt-12 flex flex-col border-t">
              {SHORTLIST.map((row) => (
                <li
                  key={row.grade}
                  className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 border-b py-5 sm:grid-cols-[auto_1fr_auto] sm:items-baseline sm:gap-x-6"
                >
                  <Badge
                    variant={row.variant}
                    className="h-6 w-7 shrink-0 justify-center self-start text-sm"
                  >
                    {row.grade}
                  </Badge>
                  <div className="min-w-0">
                    <p className="text-pretty text-base font-medium">
                      {row.title}
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {row.entity}
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      <span className="font-medium text-foreground">
                        {row.verdict}
                      </span>{" "}
                      · {row.note}
                    </p>
                  </div>
                  {/* Both figures together, right-aligned and tabular, so the
                      note stays a sentence rather than trailing a number. */}
                  <div className="col-start-2 flex gap-4 sm:col-start-3 sm:flex-col sm:gap-1 sm:text-right">
                    <p className="text-sm font-medium text-muted-foreground tabular-nums">
                      Closes in {row.closes}
                    </p>
                    <p className="text-sm text-muted-foreground tabular-nums">
                      Similarity {row.threshold}
                    </p>
                  </div>
                </li>
              ))}
            </ul>

            <p className="mt-8 max-w-prose text-pretty text-sm leading-relaxed text-muted-foreground">
              Where a notice does not state a requirement, the rule returns{" "}
              <span className="font-medium text-warning">needs checking</span>{" "}
              rather than a guess. Bidding documents are not parsed yet, so that
              happens more often than it eventually will — and you are always
              told which field it was.
            </p>
          </div>
        </section>

        {/* Close: what the next hour looks like, not the same button again. */}
        <section>
          <div className="mx-auto w-full max-w-6xl px-6 py-20 lg:px-10 lg:py-24">
            <div className="grid gap-x-14 gap-y-10 lg:grid-cols-12">
              <div className="lg:col-span-5">
                <h2 className="text-balance text-2xl font-semibold tracking-[-0.02em] sm:text-3xl">
                  Set up your profile once.
                </h2>
                <p className="mt-4 max-w-prose text-pretty text-muted-foreground">
                  Your capability profile and eligibility rules take an
                  afternoon. After that the shortlist arrives on its own, every
                  morning, at the hour you choose.
                </p>
                <div className="mt-8">
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

              <ol className="flex flex-col lg:col-span-7 lg:justify-self-end">
                {[
                  {
                    title: "Describe what you build",
                    body: "Services, past projects, sectors and the districts you work in. The matching reads this, so it is worth an hour.",
                  },
                  {
                    title: "Set the rules you actually bid under",
                    body: "Turnover floor, certifications held, years of experience, joint-venture terms.",
                  },
                  {
                    title: "Choose who hears about it, and when",
                    body: "Recipients, the digest hour in your timezone, and whether a strong match should interrupt the day.",
                  },
                ].map((step, index) => (
                  <li
                    key={step.title}
                    className="grid grid-cols-[1.5rem_1fr] gap-x-4 border-t py-5 first:border-t-0 first:pt-0"
                  >
                    <span
                      aria-hidden
                      className="text-sm leading-6 font-medium text-muted-foreground tabular-nums"
                    >
                      {index + 1}
                    </span>
                    <div>
                      <p className="text-sm leading-6 font-medium">
                        {step.title}
                      </p>
                      <p className="mt-1 max-w-prose text-pretty text-sm leading-relaxed text-muted-foreground">
                        {step.body}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-start justify-between gap-4 px-6 py-8 sm:flex-row sm:items-center lg:px-10">
          <div className="flex flex-col gap-2">
            <Logo size={22} />
            <p className="text-xs text-muted-foreground">
              Public procurement intelligence for Bangladesh and the multilateral
              development banks.
            </p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <Link
              to="/login"
              className="text-muted-foreground hover:text-foreground"
            >
              Sign in
            </Link>
            <Link to="/register" className="font-medium text-primary hover:underline">
              Create account
            </Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
