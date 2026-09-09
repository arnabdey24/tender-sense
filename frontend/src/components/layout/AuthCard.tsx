import type * as React from "react"

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

export type AuthCardProps = {
  title: React.ReactNode
  description?: React.ReactNode
  children: React.ReactNode
  footer?: React.ReactNode
}

export function AuthCard({
  title,
  description,
  children,
  footer,
}: AuthCardProps) {
  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>{children}</CardContent>
      {footer ? (
        <CardFooter className="justify-center text-sm text-muted-foreground">
          {footer}
        </CardFooter>
      ) : null}
    </Card>
  )
}
