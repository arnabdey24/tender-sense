import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterAll, afterEach, beforeAll, vi } from "vitest"

import { server } from "@/mocks/server"

// jsdom ships none of the layout APIs Base UI's popups rely on.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

// jsdom logs "Not implemented" for scrollTo; the router calls it on every nav.
window.scrollTo = vi.fn()

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn()
}

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())
