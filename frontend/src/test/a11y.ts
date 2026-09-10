import axe, { type Result, type RunOptions } from "axe-core"

/**
 * Rules that cannot be judged inside jsdom and would only ever be noise here.
 *
 * `color-contrast` needs real layout and computed styles, which jsdom does not
 * produce — it reports every element as failing, which trains people to ignore
 * the whole report. It belongs in a browser run, not this one.
 */
const JSDOM_BLIND_SPOTS = ["color-contrast"]

const OPTIONS: RunOptions = {
  resultTypes: ["violations"],
  rules: Object.fromEntries(
    JSDOM_BLIND_SPOTS.map((rule) => [rule, { enabled: false }])
  ),
}

export type Violation = Pick<Result, "id" | "impact" | "help" | "nodes">

/** Run axe over the rendered document and return only genuine violations. */
export async function findViolations(
  container: Element = document.body
): Promise<Violation[]> {
  const results = await axe.run(container, OPTIONS)
  return results.violations.map(({ id, impact, help, nodes }) => ({
    id,
    impact,
    help,
    nodes,
  }))
}

/** A readable failure: which rule, on which element, and what to do about it. */
export function describeViolations(violations: Violation[]): string {
  return violations
    .map(
      (violation) =>
        `${violation.id} (${violation.impact}): ${violation.help}\n` +
        violation.nodes
          .slice(0, 3)
          .map((node) => `    ${node.html}`)
          .join("\n")
    )
    .join("\n\n")
}
