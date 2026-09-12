/**
 * The one place the password policy is written down on the client.
 *
 * It has to agree with `password_min_length` in the backend's settings, which
 * is the only authority — the form previously said eight and the API rejected
 * anything under ten, so the hint text talked a user into a password the
 * server would not take and then blamed them for it.
 */
export const PASSWORD_MIN_LENGTH = 10

/** Said once, in the field description and in the failure, so they agree. */
export const PASSWORD_RULE = `Use at least ${PASSWORD_MIN_LENGTH} characters.`

export const STRENGTH_LABELS = [
  "Too short",
  "Weak",
  "Fair",
  "Good",
  "Strong",
] as const

/** Cheap, local-only heuristic — the backend remains the authority. */
export function passwordScore(password: string): number {
  if (!password || password.length < PASSWORD_MIN_LENGTH) return 0
  let score = 1
  if (password.length >= 12) score += 1
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1
  return Math.min(score, 4)
}
