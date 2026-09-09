export const STRENGTH_LABELS = [
  "Too short",
  "Weak",
  "Fair",
  "Good",
  "Strong",
] as const

/** Cheap, local-only heuristic — the backend remains the authority. */
export function passwordScore(password: string): number {
  if (!password || password.length < 8) return 0
  let score = 1
  if (password.length >= 12) score += 1
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1
  return Math.min(score, 4)
}
