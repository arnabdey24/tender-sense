import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox"
import { COUNTRIES, type Country } from "@/lib/data/locale"

export type CountryComboboxProps = {
  id?: string
  /** The stored ISO 3166-1 alpha-2 code, or "" when unset. */
  value: string
  onValueChange: (code: string) => void
  onBlur?: () => void
  placeholder?: string
  emptyText?: string
  "aria-invalid"?: boolean
  "aria-describedby"?: string
  name?: string
}

/**
 * Country picker that shows names but yields ISO 3166-1 alpha-2 codes, which is
 * what the API validates. Searching by code works too, so "BD" finds Bangladesh.
 */
export function CountryCombobox({
  id,
  value,
  onValueChange,
  onBlur,
  placeholder = "Select a country",
  emptyText = "No country found.",
  name,
  ...aria
}: CountryComboboxProps) {
  const selected = COUNTRIES.find((c) => c.code === value.toUpperCase()) ?? null

  return (
    <Combobox
      items={COUNTRIES}
      itemToStringLabel={(country: Country) => country.name}
      isItemEqualToValue={(a: Country, b: Country) => a.code === b.code}
      // Match on the code as well as the name, so typing "BD" finds Bangladesh.
      filter={(country: Country, query: string) => {
        const q = query.trim().toLowerCase()
        return (
          !q ||
          country.name.toLowerCase().includes(q) ||
          country.code.toLowerCase().startsWith(q)
        )
      }}
      value={selected}
      onValueChange={(next: Country | null) => onValueChange(next?.code ?? "")}
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
          {(country: Country) => (
            <ComboboxItem key={country.code} value={country}>
              {country.name}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
