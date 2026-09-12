import type { CompanyResearch } from "@/features/aiassist/api"

const KEY = "aiassist:profile-draft"

/**
 * Carry the capability half of a website reading across org creation.
 *
 * One press of Auto setup produces a draft covering both the organization
 * (name, country, description) and the capability profile (overview, sectors,
 * services). Only the first half has a form to land in at onboarding, because
 * the organization does not exist yet and so neither does its profile.
 *
 * Rather than throw the rest away and charge the user a second reading later,
 * it waits here until the capability profile page opens.
 *
 * Deliberately `sessionStorage`, and deliberately best-effort. It is an
 * optimisation on a path that works without it: the profile page offers its
 * own Auto setup button with the saved website already filled in, so a
 * private window, a blocked storage API or a different device costs one extra
 * press rather than a broken flow. Every access is guarded because reading it
 * can throw outright, not merely return null.
 */
export function stashProfileDraft(draft: CompanyResearch): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(draft))
  } catch {
    // A draft we cannot stash is a button the user presses again. Fine.
  }
}

export function takeProfileDraft(): CompanyResearch | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    // Read once: leaving it behind would re-apply the draft over edits every
    // time the page remounts, which reads as the form fighting the user.
    sessionStorage.removeItem(KEY)
    return JSON.parse(raw) as CompanyResearch
  } catch {
    return null
  }
}
