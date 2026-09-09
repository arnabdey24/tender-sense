import { UserPlusIcon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

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
import { applyFieldErrors } from "@/lib/api/call"
import { isApiError } from "@/lib/api/errors"
import { RhfField } from "@/lib/forms/RhfField"
import { useZodForm } from "@/lib/forms/useZodForm"
import { useCreateInvitation } from "@/features/org/api"
import { ROLE_ITEMS, type OrgRole } from "@/features/org/roles"

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Email is required")
    .email("Enter a valid email"),
  role: z.enum(["admin", "member"]),
})

export function InviteDialog({ disabled }: { disabled?: boolean }) {
  const [open, setOpen] = React.useState(false)
  const invite = useCreateInvitation()

  const form = useZodForm({
    schema,
    defaultValues: { email: "", role: "member" as OrgRole },
  })

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await invite.mutateAsync({ email: values.email, role: values.role })
      form.reset({ email: "", role: "member" })
      setOpen(false)
    } catch (err) {
      // The mutation already toasts; surface field-level detail inline too.
      if (isApiError(err)) applyFieldErrors(form, err, ["email", "role"])
    }
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button disabled={disabled} />}>
        <UserPlusIcon data-icon="inline-start" />
        Invite member
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
          <DialogHeader>
            <DialogTitle>Invite a teammate</DialogTitle>
            <DialogDescription>
              They will get an email with a link to join this organization.
            </DialogDescription>
          </DialogHeader>

          <FieldGroup>
            <RhfField form={form} name="email" label="Email">
              <Input
                type="email"
                autoComplete="off"
                placeholder="teammate@company.com"
              />
            </RhfField>
            <RhfField form={form} name="role" label="Role">
              {(control) => (
                <Select
                  items={ROLE_ITEMS}
                  value={control.value as OrgRole}
                  onValueChange={(value: OrgRole | null) =>
                    control.onChange(value ?? "member")
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
                      {ROLE_ITEMS.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              )}
            </RhfField>
          </FieldGroup>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={invite.isPending}>
              {invite.isPending ? <Spinner data-icon="inline-start" /> : null}
              Send invitation
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
