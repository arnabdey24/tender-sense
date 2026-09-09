import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox"

export type StringComboboxProps = {
  id?: string
  items: string[]
  value: string
  onValueChange: (value: string) => void
  onBlur?: () => void
  placeholder?: string
  emptyText?: string
  "aria-invalid"?: boolean
  "aria-describedby"?: string
  name?: string
}

/**
 * A single-select combobox over a flat list of strings — the shape both the
 * country and timezone pickers need. Keeps the Base UI plumbing in one place.
 */
export function StringCombobox({
  id,
  items,
  value,
  onValueChange,
  onBlur,
  placeholder,
  emptyText = "No matches.",
  name,
  ...aria
}: StringComboboxProps) {
  return (
    <Combobox
      items={items}
      value={value || null}
      onValueChange={(next: string | null) => onValueChange(next ?? "")}
      name={name}
    >
      <ComboboxInput
        id={id}
        placeholder={placeholder}
        onBlur={onBlur}
        aria-invalid={aria["aria-invalid"]}
        aria-describedby={aria["aria-describedby"]}
      />
      <ComboboxContent>
        <ComboboxEmpty>{emptyText}</ComboboxEmpty>
        <ComboboxList>
          {(item: string) => (
            <ComboboxItem key={item} value={item}>
              {item}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
