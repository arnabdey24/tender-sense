import type { DataTableColumn } from "@/components/ui/data-table"

/**
 * The tender pool's columns, and which of them a reader may put away.
 *
 * The notice and its deadline are fixed: one is the row's identity and the
 * other is the field the product treats as decisive, so neither is hideable.
 */
export const TENDER_COLUMNS: DataTableColumn[] = [
  { id: "notice", label: "Notice", fixed: true },
  { id: "buyer", label: "Buyer" },
  { id: "category", label: "Category" },
  { id: "source", label: "Source" },
  { id: "value", label: "Value" },
  { id: "published", label: "Published" },
  { id: "closes", label: "Closes", fixed: true },
]
