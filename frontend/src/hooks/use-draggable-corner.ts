import * as React from "react"

import { usePersistentState } from "@/hooks/use-persistent-state"

export type CornerOffset = { right: number; bottom: number }

/**
 * Lets a corner-anchored floating element be dragged anywhere and stay there.
 *
 * Anchored by distance from the bottom-right rather than by absolute
 * coordinates, so the element keeps its relationship to the corner when the
 * window is resized instead of drifting off-screen or landing under the
 * scrollbar. Whatever is stored is still clamped on mount and on every
 * resize, because a position saved on a 27-inch monitor is off-screen on a
 * laptop.
 *
 * A press that never travels more than a few pixels is a click, not a drag —
 * without that threshold the button would swallow every activation, since a
 * pointer always moves a little between down and up.
 */
const DRAG_THRESHOLD = 4

export function useDraggableCorner({
  storageKey,
  defaultOffset,
  size,
}: {
  storageKey: string
  defaultOffset: CornerOffset
  /** Element footprint, used to keep it fully on screen. */
  size: { width: number; height: number }
}) {
  const [offset, setOffset] = usePersistentState<CornerOffset>(
    storageKey,
    defaultOffset
  )
  const [dragging, setDragging] = React.useState(false)
  const origin = React.useRef<{
    x: number
    y: number
    right: number
    bottom: number
  } | null>(null)
  const moved = React.useRef(false)

  const clamp = React.useCallback(
    (next: CornerOffset): CornerOffset => {
      const maxRight = Math.max(0, window.innerWidth - size.width)
      const maxBottom = Math.max(0, window.innerHeight - size.height)
      return {
        right: Math.min(Math.max(8, next.right), maxRight),
        bottom: Math.min(Math.max(8, next.bottom), maxBottom),
      }
    },
    [size.width, size.height]
  )

  // A stored position from a larger window has to be pulled back into view.
  React.useEffect(() => {
    const reclamp = () => setOffset((prev) => clamp(prev))
    reclamp()
    window.addEventListener("resize", reclamp)
    return () => window.removeEventListener("resize", reclamp)
  }, [clamp, setOffset])

  const onPointerDown = React.useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      // Left button or touch only; a right-click must still open the menu.
      if (event.button !== 0) return
      origin.current = {
        x: event.clientX,
        y: event.clientY,
        right: offset.right,
        bottom: offset.bottom,
      }
      moved.current = false
      event.currentTarget.setPointerCapture(event.pointerId)
    },
    [offset.right, offset.bottom]
  )

  const onPointerMove = React.useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      const start = origin.current
      if (!start) return
      const dx = event.clientX - start.x
      const dy = event.clientY - start.y
      if (!moved.current && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
      moved.current = true
      setDragging(true)
      // Dragging right reduces the distance from the right edge, hence the
      // inverted signs.
      setOffset(clamp({ right: start.right - dx, bottom: start.bottom - dy }))
    },
    [clamp, setOffset]
  )

  const endDrag = React.useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      if (origin.current) {
        event.currentTarget.releasePointerCapture?.(event.pointerId)
      }
      origin.current = null
      setDragging(false)
    },
    []
  )

  /** True when the gesture that just ended was a drag, so a click is ignored. */
  const consumeDrag = React.useCallback(() => {
    const was = moved.current
    moved.current = false
    return was
  }, [])

  return {
    offset,
    dragging,
    consumeDrag,
    reset: React.useCallback(
      () => setOffset(defaultOffset),
      [setOffset, defaultOffset]
    ),
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp: endDrag,
      onPointerCancel: endDrag,
    },
  }
}
