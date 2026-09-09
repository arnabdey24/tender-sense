import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_app/app/")({
  beforeLoad: () => {
    throw redirect({ to: "/app/dashboard" })
  },
})
