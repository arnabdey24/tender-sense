import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export type FilterOption = { value: string; label: string; count?: number }

/**
 * A single-select filter with an "any" reset entry. Base UI's Select needs the
 * full item list up front so it can render the trigger label.
 */
export function TenderFilterSelect({
  label,
  value,
  options,
  onChange,
  anyLabel = "Any",
}: {
  label: string
  value: string | undefined
  options: FilterOption[]
  onChange: (value: string | undefined) => void
  anyLabel?: string
}) {
  const ANY = "__any__"
  const items = [{ value: ANY, label: anyLabel }, ...options]

  return (
    <Select
      items={items}
      value={value ?? ANY}
      onValueChange={(next: string | null) =>
        onChange(!next || next === ANY ? undefined : next)
      }
    >
      <SelectTrigger size="sm" className="w-full" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
              {"count" in item && item.count !== undefined
                ? ` (${item.count})`
                : ""}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}
