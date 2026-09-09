import { createFileRoute, Link } from "@tanstack/react-router"
import { ChevronRightIcon, UserRoundIcon, UsersIcon } from "lucide-react"

import { PageHeader } from "@/components/layout/PageHeader"
import { Item, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"

export const Route = createFileRoute("/_app/app/settings/")({
  component: Page,
})

const SECTIONS = [
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
] as const

function Page() {
  return (
    <>
      <PageHeader
        title="Settings"
        description="Manage your profile, organization, and preferences."
      />
      <ItemGroup className="max-w-2xl gap-2">
        {SECTIONS.map((section) => (
          <Item
            key={section.to}
            variant="outline"
            render={<Link to={section.to} />}
          >
            <ItemMedia variant="icon">
              <section.icon />
            </ItemMedia>
            <ItemContent>
              <ItemTitle>{section.title}</ItemTitle>
              <ItemDescription>{section.description}</ItemDescription>
            </ItemContent>
            <ChevronRightIcon className="text-muted-foreground" />
          </Item>
        ))}
      </ItemGroup>
    </>
  )
}
