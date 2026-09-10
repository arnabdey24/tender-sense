import * as React from "react"
import {
  ArrowDownIcon,
  ArrowUpIcon,
  ChevronsUpDownIcon,
  Columns3Icon,
  Rows2Icon,
  Rows3Icon,
  XIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { TableHead } from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { usePersistentState } from "@/hooks/use-persistent-state"
import { cn } from "@/lib/utils"

/**
 * The parts every list surface in this product needs, and had been rebuilding.
 *
 * Deliberately not a generic table engine. The cells here carry real product
 * judgement — a deadline's tone, a grade's rail, a value that is usually
 * absent — and a `columns={[...]}` abstraction would have flattened all of it
 * into renderers. What is actually shared is the machinery around the cells:
 * density, selection, column visibility, sorting affordances and keyboard
 * movement. Those live here; the cells stay where they belong.
 */
export type Density = "comfortable" | "compact"

export type DataTableColumn = {
  id: string
  label: string
  /** Columns that carry the row's identity cannot be hidden. */
  fixed?: boolean
}

type DataTableValue = {
  density: Density
  setDensity: (d: Density) => void
  columns: DataTableColumn[]
  isVisible: (id: string) => boolean
  toggleColumn: (id: string) => void
  rowIds: string[]
  selected: ReadonlySet<string>
  isSelected: (id: string) => boolean
  toggleRow: (id: string, extendRange?: boolean) => void
  toggleAll: () => void
  clearSelection: () => void
  allSelected: boolean
  someSelected: boolean
  activeId: string | null
  setActiveId: (id: string | null) => void
}

const DataTableContext = React.createContext<DataTableValue | null>(null)

export function useDataTableContext() {
  const ctx = React.useContext(DataTableContext)
  if (!ctx) {
    throw new Error("DataTable parts must be used inside <DataTableProvider>")
  }
  return ctx
}

export function useDataTable({
  rowIds,
  storageKey,
  columns = [],
  defaultHidden = [],
}: {
  rowIds: string[]
  /** Namespaces the persisted density and column choices per surface. */
  storageKey: string
  columns?: DataTableColumn[]
  /** Columns that start hidden — a field that is usually absent earns a
      place in the menu, not in the default six columns of a dense table. */
  defaultHidden?: string[]
}): DataTableValue {
  const [density, setDensity] = usePersistentState<Density>(
    `${storageKey}:density`,
    "comfortable"
  )
  const [hidden, setHidden] = usePersistentState<string[]>(
    `${storageKey}:hidden-columns`,
    defaultHidden
  )
  const [selected, setSelected] = React.useState<ReadonlySet<string>>(
    () => new Set()
  )
  const [activeId, setActiveId] = React.useState<string | null>(null)
  const lastToggled = React.useRef<string | null>(null)

  // A selection that survives a page change would let a bulk action reach rows
  // the user can no longer see, so it is dropped whenever the rows change.
  // Adjusted during render rather than in an effect — React's own "adjust
  // state on prop change" pattern, as the search box on this page already does.
  // The range anchor is deliberately left alone: once its row is gone,
  // `indexOf` returns -1 and the shift-range branch falls through to a plain
  // toggle, which is the correct behaviour anyway.
  const rowKey = rowIds.join(",")
  const [seenRowKey, setSeenRowKey] = React.useState(rowKey)
  if (seenRowKey !== rowKey) {
    setSeenRowKey(rowKey)
    if (selected.size > 0) setSelected(new Set())
  }

  const toggleRow = React.useCallback(
    (id: string, extendRange = false) => {
      setSelected((prev) => {
        const next = new Set(prev)
        const anchor = lastToggled.current
        // Shift-click fills from the last row touched to this one, which is
        // the behaviour every desktop list has taught people to expect.
        if (extendRange && anchor && anchor !== id) {
          const from = rowIds.indexOf(anchor)
          const to = rowIds.indexOf(id)
          if (from !== -1 && to !== -1) {
            const [lo, hi] = from < to ? [from, to] : [to, from]
            const selecting = !prev.has(id)
            for (let i = lo; i <= hi; i++) {
              if (selecting) next.add(rowIds[i])
              else next.delete(rowIds[i])
            }
            lastToggled.current = id
            return next
          }
        }
        if (next.has(id)) next.delete(id)
        else next.add(id)
        lastToggled.current = id
        return next
      })
    },
    [rowIds]
  )

  const allSelected = rowIds.length > 0 && selected.size === rowIds.length
  const someSelected = selected.size > 0 && !allSelected

  const toggleAll = React.useCallback(() => {
    setSelected((prev) =>
      prev.size === rowIds.length ? new Set() : new Set(rowIds)
    )
    lastToggled.current = null
  }, [rowIds])

  const clearSelection = React.useCallback(() => {
    setSelected(new Set())
    lastToggled.current = null
  }, [])

  const hiddenSet = React.useMemo(() => new Set(hidden), [hidden])

  const toggleColumn = React.useCallback(
    (id: string) => {
      setHidden((prev) =>
        prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]
      )
    },
    [setHidden]
  )

  return {
    density,
    setDensity,
    columns,
    isVisible: React.useCallback((id) => !hiddenSet.has(id), [hiddenSet]),
    toggleColumn,
    rowIds,
    selected,
    isSelected: React.useCallback((id) => selected.has(id), [selected]),
    toggleRow,
    toggleAll,
    clearSelection,
    allSelected,
    someSelected,
    activeId,
    setActiveId,
  }
}

export function DataTableProvider({
  value,
  children,
}: {
  value: DataTableValue
  children: React.ReactNode
}) {
  return (
    <DataTableContext.Provider value={value}>
      {children}
    </DataTableContext.Provider>
  )
}

/**
 * The density attribute lives on a wrapper so every row inside inherits it
 * through CSS custom properties rather than a class on each cell.
 */
export function DataTableSurface({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const { density } = useDataTableContext()
  return (
    <div data-density={density} className={cn("min-w-0", className)} {...props} />
  )
}

export function DataTableToolbar({
  filters,
  children,
  className,
  ...props
}: React.ComponentProps<"div"> & { filters?: React.ReactNode }) {
  return (
    <div
      data-slot="data-table-toolbar"
      className={cn(
        "flex flex-wrap items-center gap-2 md:flex-nowrap",
        className
      )}
      {...props}
    >
      {filters ? (
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          {filters}
        </div>
      ) : null}
      {children ? (
        <div className="ml-auto flex shrink-0 items-center gap-1">
          {children}
        </div>
      ) : null}
    </div>
  )
}

export function DataTableDensityToggle() {
  const { density, setDensity } = useDataTableContext()
  const next = density === "comfortable" ? "compact" : "comfortable"

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Switch to ${next} rows`}
            onClick={() => setDensity(next)}
          >
            {density === "comfortable" ? <Rows3Icon /> : <Rows2Icon />}
          </Button>
        }
      />
      <TooltipContent>
        {density === "comfortable" ? "Compact rows" : "Comfortable rows"}
      </TooltipContent>
    </Tooltip>
  )
}

export function DataTableColumnsMenu() {
  const { columns, isVisible, toggleColumn } = useDataTableContext()
  const hideable = columns.filter((c) => !c.fixed)
  if (hideable.length === 0) return null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="icon-sm" aria-label="Choose columns">
            <Columns3Icon />
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-44">
        {/* The label is Base UI's `Menu.GroupLabel`, which reads its group
            from context — outside a `Menu.Group` it throws rather than
            rendering unlabelled. */}
        <DropdownMenuGroup>
          <DropdownMenuLabel>Columns</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {hideable.map((column) => (
            <DropdownMenuCheckboxItem
              key={column.id}
              checked={isVisible(column.id)}
              onCheckedChange={() => toggleColumn(column.id)}
            >
              {column.label}
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/**
 * Replaces the toolbar in place while rows are selected.
 *
 * Appearing *below* the toolbar would push the table down and move the row the
 * user just clicked out from under their cursor, so it occupies the same band
 * instead and the layout never shifts.
 */
export function DataTableSelectionBar({
  children,
  className,
  ...props
}: React.ComponentProps<"div">) {
  const { selected, clearSelection } = useDataTableContext()
  if (selected.size === 0) return null

  return (
    <div
      data-slot="data-table-selection-bar"
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-lg bg-surface-sunken px-2 py-1.5 ring-1 ring-foreground/10",
        className
      )}
      {...props}
    >
      <span
        aria-live="polite"
        className="px-1 text-sm font-medium tabular-nums"
      >
        {selected.size} selected
      </span>
      <div className="ml-auto flex flex-wrap items-center gap-1">
        {children}
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Clear selection"
          onClick={clearSelection}
        >
          <XIcon />
        </Button>
      </div>
    </div>
  )
}

export function DataTableSelectAll() {
  const { allSelected, someSelected, toggleAll, rowIds } =
    useDataTableContext()
  return (
    <Checkbox
      checked={allSelected}
      indeterminate={someSelected}
      onCheckedChange={toggleAll}
      disabled={rowIds.length === 0}
      aria-label={allSelected ? "Clear selection" : "Select all rows on this page"}
    />
  )
}

export function DataTableRowCheckbox({
  id,
  label,
}: {
  id: string
  label: string
}) {
  const { isSelected, toggleRow } = useDataTableContext()
  return (
    <Checkbox
      checked={isSelected(id)}
      aria-label={`Select ${label}`}
      // Base UI hands back the value, not the event, so the modifier is read
      // from the click that produced it.
      onClick={(event) => {
        event.stopPropagation()
        toggleRow(id, event.shiftKey)
      }}
      onCheckedChange={() => {
        /* handled in onClick so the shift modifier is available */
      }}
    />
  )
}

export type SortDirection = "asc" | "desc"

export function SortableHead({
  active,
  direction,
  onSort,
  align = "start",
  children,
  className,
  ...props
}: Omit<React.ComponentProps<typeof TableHead>, "onSort" | "align"> & {
  active: boolean
  direction: SortDirection
  onSort: () => void
  /** `end` mirrors the control for a right-aligned numeric column. */
  align?: "start" | "end"
}) {
  const Icon = !active
    ? ChevronsUpDownIcon
    : direction === "asc"
      ? ArrowUpIcon
      : ArrowDownIcon

  return (
    <TableHead
      aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}
      className={cn("p-0", className)}
      {...props}
    >
      <button
        type="button"
        onClick={onSort}
        className={cn(
          "flex h-9 w-full items-center gap-1 px-2 text-[11px] font-medium tracking-[0.04em] uppercase whitespace-nowrap transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset",
          align === "end" && "justify-end",
          active ? "text-foreground" : "text-muted-foreground"
        )}
      >
        {align === "end" ? (
          <>
            <Icon
              className={cn("size-3", !active && "opacity-0 transition-opacity group-hover/head:opacity-60")}
              aria-hidden
            />
            {children}
          </>
        ) : (
          <>
            {children}
            <Icon
              className={cn("size-3", !active && "opacity-0 transition-opacity group-hover/head:opacity-60")}
              aria-hidden
            />
          </>
        )}
      </button>
    </TableHead>
  )
}

/**
 * Keyboard movement for a list of rows.
 *
 * `j`/`k` and the arrows move, `x` selects, Enter opens. Bound to the
 * container rather than the window, and ignored entirely while the caret is
 * in a field, so typing "jack" into the search box does not walk the table.
 */
export function useDataTableKeyboard({
  onOpen,
}: {
  onOpen?: (id: string) => void
} = {}) {
  const { rowIds, activeId, setActiveId, toggleRow } = useDataTableContext()

  return React.useCallback(
    (event: React.KeyboardEvent<HTMLElement>) => {
      const target = event.target as HTMLElement | null
      if (
        target?.closest("input, textarea, select, [contenteditable='true']")
      ) {
        return
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (rowIds.length === 0) return

      const index = activeId ? rowIds.indexOf(activeId) : -1
      const focus = (next: number) => {
        const id = rowIds[Math.max(0, Math.min(rowIds.length - 1, next))]
        setActiveId(id)
        const el = event.currentTarget.querySelector<HTMLElement>(
          `[data-row-id="${CSS.escape(id)}"]`
        )
        el?.focus()
        el?.scrollIntoView({ block: "nearest" })
      }

      switch (event.key) {
        case "j":
        case "ArrowDown":
          event.preventDefault()
          focus(index + 1)
          break
        case "k":
        case "ArrowUp":
          event.preventDefault()
          focus(index === -1 ? 0 : index - 1)
          break
        case "x":
          if (activeId) {
            event.preventDefault()
            toggleRow(activeId)
          }
          break
        case "Enter":
          if (activeId && onOpen) {
            event.preventDefault()
            onOpen(activeId)
          }
          break
        default:
          break
      }
    },
    [rowIds, activeId, setActiveId, toggleRow, onOpen]
  )
}
