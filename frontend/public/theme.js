/*
 * Resolve the theme before first paint. Without this a dark-mode user gets a
 * full white frame while the bundle loads. Mirrors the contract in
 * src/components/theme-provider.tsx: key "theme", values light|dark|system.
 *
 * A file rather than an inline script, because the SPA is served under
 * `script-src 'self'` (infra/caddy/Caddyfile) — which blocked the inline
 * version outright. The script written to prevent the flash was, in every
 * deployment behind that proxy, the one thing on the page guaranteed not to
 * run. Same-origin is the fix that keeps the policy strict; a hash would work
 * too, and would break silently the next time someone edited the script.
 */
;(function () {
  try {
    var stored = localStorage.getItem("theme")
    var theme =
      stored === "light" || stored === "dark"
        ? stored
        : window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
    document.documentElement.classList.add(theme)
  } catch (e) {
    /* Private mode or blocked storage: the provider settles it on mount. */
  }
})()
