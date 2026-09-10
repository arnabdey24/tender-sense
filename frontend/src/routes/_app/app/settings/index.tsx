import { createFileRoute, Link } from "@tanstack/react-router"
import {
  BellIcon,
  Building2Icon,
  SatelliteDishIcon,
  ScaleIcon,
  WrenchIcon,
  UserRoundIcon,
  UsersIcon,
} from "lucide-react"

import { PageHeader } from "@/components/layout/PageHeader"

export const Route = createFileRoute("/_app/app/settings/")({
  component: Page,
})

/**
 * Grouped by the question each answers, not listed flat.
 *
 * Seven identical outlined cards, each icon-plus-heading-plus-text, was the page
 * structure — the lazy container repeated until it filled a column, saying
 * nothing about how the settings relate. Three named groups say which of them
 * change what tenders reach you, and which are housekeeping.
 */
const GROUPS = [
  {
    heading: "What you are matched on",
    caption:
      "These decide which notices reach you at all, and how they are graded.",
    items: [
      {
        to: "/app/settings/profile",
        icon: WrenchIcon,
        title: "Capability profile",
        description: "What you do — this is what tenders are matched against.",
      },
      {
        to: "/app/settings/rules",
        icon: ScaleIcon,
        title: "Bidding criteria",
        description: "Rules that decide which tenders you can actually bid on.",
      },
      {
        to: "/app/settings/sources",
        icon: SatelliteDishIcon,
        title: "Sources",
        description:
          "The procurement portals we watch, and whether they answer.",
      },
    ],
  },
  {
    heading: "How you hear about it",
    caption: "Nothing is emailed until an address here is verified.",
    items: [
      {
        to: "/app/settings/notifications",
        icon: BellIcon,
        title: "Notifications",
        description:
          "What you are told about, when, and which addresses hear it.",
      },
    ],
  },
  {
    heading: "Your company and your account",
    caption: null,
    items: [
      {
        to: "/app/settings/organization",
        icon: Building2Icon,
        title: "Organization",
        description: "Company name, country, timezone and website.",
      },
      {
        to: "/app/settings/members",
        icon: UsersIcon,
        title: "Members",
        description: "Invite teammates and manage their roles.",
      },
      {
        to: "/account",
        icon: UserRoundIcon,
        title: "Account",
        description: "Your profile, password, and sessions.",
      },
    ],
  },
] as const

function Page() {
  return (
    <>
      <PageHeader
        title="Settings"
        description="Manage your profile, organization, and preferences."
      />

      <div className="flex max-w-5xl flex-col gap-10">
        {GROUPS.map((group) => (
          <section
            key={group.heading}
            className="grid gap-x-10 gap-y-4 lg:grid-cols-12"
          >
            <div className="lg:col-span-4">
              <h2 className="font-heading text-base font-medium">
                {group.heading}
              </h2>
              {group.caption ? (
                <p className="mt-1.5 text-sm leading-relaxed text-pretty text-muted-foreground">
                  {group.caption}
                </p>
              ) : null}
            </div>

            <ul className="flex flex-col lg:col-span-8">
              {group.items.map((item) => (
                <li key={item.to} className="border-t first:border-t-0">
                  <Link
                    to={item.to}
                    className="group flex items-start gap-3 rounded-lg px-2 py-3.5 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring"
                  >
                    <item.icon className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium">
                        {item.title}
                      </span>
                      <span className="mt-0.5 block text-sm text-pretty text-muted-foreground">
                        {item.description}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  )
}
