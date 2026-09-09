import { zodResolver } from "@hookform/resolvers/zod"
import {
  useForm,
  type FieldValues,
  type Resolver,
  type UseFormProps,
  type UseFormReturn,
} from "react-hook-form"
import type { z } from "zod"

type ZodObjectSchema = z.ZodType<FieldValues, FieldValues>

export type UseZodFormProps<TSchema extends ZodObjectSchema> = Omit<
  UseFormProps<z.input<TSchema>, unknown, z.output<TSchema>>,
  "resolver"
> & {
  schema: TSchema
}

/**
 * `useForm` pre-wired with a zod resolver and `mode: "onBlur"`.
 * Pair with `<RhfField>` for shadcn Field markup.
 */
export function useZodForm<TSchema extends ZodObjectSchema>({
  schema,
  mode = "onBlur",
  ...props
}: UseZodFormProps<TSchema>): UseFormReturn<
  z.input<TSchema>,
  unknown,
  z.output<TSchema>
> {
  return useForm<z.input<TSchema>, unknown, z.output<TSchema>>({
    ...props,
    mode,
    // zodResolver's overloads cannot see through the generic schema; the
    // runtime behaviour is identical, so narrow the resolver type explicitly.
    resolver: zodResolver(schema) as unknown as Resolver<
      z.input<TSchema>,
      unknown,
      z.output<TSchema>
    >,
  })
}
