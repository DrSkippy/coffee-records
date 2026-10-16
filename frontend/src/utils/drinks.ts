import type { DrinkType } from "../types";

// Makers whose New Shot drink defaults differ from the stored default
// (Defaults page). Maker names match case-insensitively.
export const MAKER_DRINK_DEFAULTS: Readonly<Record<string, DrinkType>> = {
  Sara: "cappuccino",
};

/** The drink a new shot should start with for this maker. */
export const defaultDrinkFor = (maker: string, storedDefault: string): string => {
  const wanted = maker.trim().toLowerCase();
  const match = Object.entries(MAKER_DRINK_DEFAULTS).find(
    ([name]) => name.toLowerCase() === wanted
  );
  return match ? match[1] : storedDefault;
};

/**
 * The drink field's value after the maker changes: the maker's default, unless
 * the user (or an import) already chose a drink, which is always kept.
 */
export const nextDrinkValue = (
  maker: string,
  storedDefault: string,
  current: string,
  drinkChosen: boolean
): string => (drinkChosen ? current : defaultDrinkFor(maker, storedDefault));
