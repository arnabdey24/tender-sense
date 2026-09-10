import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRightIcon } from "lucide-react"

import { Logo, LogoMark } from "@/components/brand/Logo"
import { ThemeToggle } from "@/components/layout/ThemeToggle"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

export const Route = createFileRoute("/")({
  component: LandingPage,
})

/**
 * The order is the product: a notice is only worth grading once it has been
 * read, and only worth alerting on once the rules have run. So the sequence is
 * numbered — the numbers carry information here rather than decorating.
 */
const PIPELINE = [
  {
    title: "It reads the portals",
    body: "e-GP Bangladesh and the World Bank procurement feed, polled for new notices and re-read when one is corrected. English, Bangla, or a mix of both.",
  },
  {
    title: "It matches on meaning",
    body: "Your capability profile — services, past projects, sectors, geographies — is compared against the substance of each notice, not against a keyword list. A road-maintenance tender still matches a firm that wrote “highway rehabilitation”.",
  },
  {
    title: "It applies your rules",
    body: "Minimum turnover, required certifications, years of experience, joint-venture terms. Your thresholds, evaluated the same way every time, with BDT and USD compared through recorded rates.",
  },
  {
    title: "It grades, and shows its work",
    body: "Every grade opens onto the quoted line it came from, which rule passed or failed, and which version of your profile produced it. Where the notice does not say, it says so.",
  },
  {
    title: "It tells you in time",
    body: "A ranked digest each morning at your hour, an instant alert when a strong fit is also eligible, and reminders as the deadline approaches on anything you marked to bid.",
  },
] as const

const GRADES = [
  { grade: "S", variant: "gradeS", label: "Bid", note: "Similarity 0.78 and above" },
  { grade: "A", variant: "gradeA", label: "Bid", note: "0.70 and above" },
  { grade: "B", variant: "gradeB", label: "Hold", note: "0.62 and above" },
  { grade: "C", variant: "gradeC", label: "Skip", note: "Below 0.62" },
] as const

function LandingPage() {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="material-chrome sticky top-0 z-20 border-b">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center gap-3 px-6">
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
        {/* Hero */}
        <section className="relative border-b">
          <div className="relative mx-auto flex w-full max-w-5xl flex-col items-center gap-8 px-6 py-24 text-center sm:py-32">
            <LogoMark
              size={64}
              detail="full"
              className="logo-signal size-16 text-primary"
            />
            <div className="flex max-w-2xl flex-col gap-5">
              <h1 className="text-balance text-4xl font-semibold tracking-[-0.028em] sm:text-5xl sm:leading-[1.06]">
                Know which tenders are worth bidding, before the day starts.
              </h1>
              <p className="text-pretty text-lg leading-relaxed text-muted-foreground">
                TenderSense reads every new public procurement notice, matches it
                against what your company can actually deliver, checks it against
                your own eligibility rules, and grades it — with the evidence
                attached, so you can check the answer rather than trust it.
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-3">
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
          </div>
        </section>

        {/* Pipeline */}
        <section className="mx-auto w-full max-w-3xl px-6 py-20 sm:py-24">
          <h2 className="text-balance text-2xl font-semibold tracking-[-0.018em] sm:text-3xl">
            What happens between a notice publishing and you hearing about it
          </h2>
          <ol className="mt-10 flex flex-col">
            {PIPELINE.map((step, index) => (
              <li
                key={step.title}
                className="grid grid-cols-[auto_1fr] gap-x-5 gap-y-2 border-t py-7 first:border-t-0 first:pt-0"
              >
                <span
                  aria-hidden
                  className="mt-0.5 flex size-7 items-center justify-center rounded-full bg-accent text-[0.8rem] font-medium text-accent-foreground tabular-nums"
                >
                  {index + 1}
                </span>
                <h3 className="self-center text-base font-medium">
                  {step.title}
                </h3>
                <p className="col-start-2 text-pretty text-sm leading-relaxed text-muted-foreground">
                  {step.body}
                </p>
              </li>
            ))}
          </ol>
        </section>

        {/* Grades */}
        <section className="border-y bg-muted/40">
          <div className="mx-auto w-full max-w-3xl px-6 py-20 sm:py-24">
            <h2 className="text-balance text-2xl font-semibold tracking-[-0.018em] sm:text-3xl">
              Four grades, and a recommendation you can argue with
            </h2>
            <p className="mt-4 max-w-xl text-pretty text-sm leading-relaxed text-muted-foreground">
              The grade comes from how closely the notice matches your profile.
              The recommendation comes from the grade <em>and</em> your
              eligibility rules — a perfect match you are not qualified for is
              still a skip, and it will tell you which requirement stopped it.
            </p>

            <dl className="mt-10 flex flex-col">
              {GRADES.map((row) => (
                <div
                  key={row.grade}
                  className="flex items-center gap-4 border-t py-4 first:border-t-0"
                >
                  <dt className="w-8 shrink-0">
                    <Badge variant={row.variant} className="w-7 justify-center">
                      {row.grade}
                    </Badge>
                  </dt>
                  <dd className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="text-sm font-medium">{row.label}</span>
                    <span className="text-sm text-muted-foreground tabular-nums">
                      {row.note}
                    </span>
                  </dd>
                </div>
              ))}
            </dl>

            <p className="mt-8 max-w-xl text-pretty text-sm leading-relaxed text-muted-foreground">
              When a notice does not state a requirement, the rule returns{" "}
              <span className="font-medium text-warning">needs verification</span>{" "}
              rather than a guess. Bidding documents are not parsed yet, so that
              happens more often than it eventually will — and you will always be
              told which field it was.
            </p>
          </div>
        </section>

        {/* Close */}
        <section className="mx-auto w-full max-w-3xl px-6 py-20 text-center sm:py-24">
          <h2 className="text-balance text-2xl font-semibold tracking-[-0.018em] sm:text-3xl">
            Set up your profile once.
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-pretty text-muted-foreground">
            Your capability profile and eligibility rules take an afternoon.
            After that, the shortlist arrives on its own.
          </p>
          <Button
            size="lg"
            className="mt-8"
            render={<Link to="/register" />}
            nativeButton={false}
          >
            Create account
            <ArrowRightIcon data-icon="inline-end" />
          </Button>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-5xl flex-col items-center justify-between gap-4 px-6 py-8 sm:flex-row">
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
