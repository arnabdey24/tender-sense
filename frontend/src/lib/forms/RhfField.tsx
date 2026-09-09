import * as React from "react"
import {
  Controller,
  type ControllerRenderProps,
  type FieldPath,
  type FieldValues,
  type UseFormReturn,
} from "react-hook-form"

import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field"

type ControlProps = ControllerRenderProps<FieldValues, string> & {
  id: string
  "aria-invalid": boolean
  "aria-describedby"?: string
}

export type RhfFieldProps<
  TFieldValues extends FieldValues,
  TName extends FieldPath<TFieldValues>,
> = {
  form: UseFormReturn<TFieldValues, unknown, FieldValues>
  name: TName
  label?: React.ReactNode
  description?: React.ReactNode
  /**
   * Block content rendered after the description, such as a strength meter.
   * `FieldDescription` is a `<p>`, so a `<div>` inside it is invalid HTML and
   * React reports a hydration error.
   */
  below?: React.ReactNode
  orientation?: React.ComponentProps<typeof Field>["orientation"]
  className?: string
  /**
   * A single control element (Input, Textarea, Checkbox…). It is cloned with
   * the RHF field props (`value`, `onChange`, `onBlur`, `name`, `ref`) plus
   * `id` and `aria-invalid`. Pass a render function for custom controls.
   */
  children: React.ReactElement | ((control: ControlProps) => React.ReactNode)
}

/**
 * Bridges react-hook-form to the shadcn `Field` composition:
 * `<Field data-invalid>` + `FieldLabel` + control (`aria-invalid`) +
 * `FieldDescription` + `FieldError`.
 */
export function RhfField<
  TFieldValues extends FieldValues,
  TName extends FieldPath<TFieldValues>,
>({
  form,
  name,
  label,
  description,
  below,
  orientation,
  className,
  children,
}: RhfFieldProps<TFieldValues, TName>) {
  const id = React.useId()
  const descriptionId = description ? `${id}-description` : undefined

  return (
    <Controller
      control={form.control}
      name={name}
      render={({ field, fieldState }) => {
        const invalid = !!fieldState.error
        const control: ControlProps = {
          ...(field as ControllerRenderProps<FieldValues, string>),
          id,
          "aria-invalid": invalid,
          "aria-describedby": descriptionId,
        }

        return (
          <Field
            data-invalid={invalid || undefined}
            data-disabled={field.disabled || undefined}
            orientation={orientation}
            className={className}
          >
            {label ? <FieldLabel htmlFor={id}>{label}</FieldLabel> : null}
            {typeof children === "function"
              ? children(control)
              : React.cloneElement(children, control)}
            {description ? (
              <FieldDescription id={descriptionId}>
                {description}
              </FieldDescription>
            ) : null}
            {below}
            <FieldError errors={[fieldState.error]} />
          </Field>
        )
      }}
    />
  )
}
