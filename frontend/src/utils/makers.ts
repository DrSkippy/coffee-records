export const PRIMARY_MAKERS = ["Scott", "Sara"];

// Shots made before 9:30 am default to Scott; from 9:30 am on, to Sara.
const MORNING_CUTOFF_MINUTES = 9 * 60 + 30;

export const defaultMakerAt = (when: Date): string =>
  when.getHours() * 60 + when.getMinutes() < MORNING_CUTOFF_MINUTES ? "Scott" : "Sara";

/** Scott and Sara first, then everyone else alphabetically; duplicates ignore case. */
export const makerOptions = (...names: (string | null | undefined)[]): string[] => {
  const seen = new Set(PRIMARY_MAKERS.map((n) => n.toLowerCase()));
  const others: string[] = [];
  for (const raw of names) {
    const name = raw?.trim();
    if (name && !seen.has(name.toLowerCase())) {
      seen.add(name.toLowerCase());
      others.push(name);
    }
  }
  return [
    ...PRIMARY_MAKERS,
    ...others.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" })),
  ];
};
