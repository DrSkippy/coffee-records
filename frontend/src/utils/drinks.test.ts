import { describe, expect, it } from "vitest";
import { defaultDrinkFor, MAKER_DRINK_DEFAULTS, nextDrinkValue } from "./drinks";
import { defaultMakerAt } from "./makers";

const STORED = "americano"; // the Defaults page value

describe("defaultDrinkFor", () => {
  it("defaults Sara to cappuccino", () => {
    expect(defaultDrinkFor("Sara", STORED)).toBe("cappuccino");
  });

  it("matches the maker name case-insensitively and ignores spaces", () => {
    expect(defaultDrinkFor("  sara ", STORED)).toBe("cappuccino");
  });

  it("uses the stored default for Scott and other makers", () => {
    expect(defaultDrinkFor("Scott", STORED)).toBe("americano");
    expect(defaultDrinkFor("Guest", STORED)).toBe("americano");
    expect(defaultDrinkFor("Scott", "")).toBe("");
  });

  it("only lists drinks the API accepts", () => {
    expect(Object.values(MAKER_DRINK_DEFAULTS)).toEqual(["cappuccino"]);
  });
});

describe("nextDrinkValue", () => {
  it("follows the maker while the drink is untouched", () => {
    expect(nextDrinkValue("Sara", STORED, "americano", false)).toBe("cappuccino");
    expect(nextDrinkValue("Scott", STORED, "cappuccino", false)).toBe("americano");
  });

  it("keeps a drink the user already chose", () => {
    expect(nextDrinkValue("Sara", STORED, "latte", true)).toBe("latte");
    expect(nextDrinkValue("Scott", STORED, "cappuccino", true)).toBe("cappuccino");
    expect(nextDrinkValue("Sara", STORED, "", true)).toBe(""); // cleared on purpose
  });
});

describe("time-based maker feeds the drink default", () => {
  it("starts Sara's shots (9:30 am onward) as cappuccino", () => {
    const maker = defaultMakerAt(new Date(2026, 9, 16, 9, 30));
    expect(maker).toBe("Sara");
    expect(defaultDrinkFor(maker, STORED)).toBe("cappuccino");
  });

  it("starts Scott's shots (before 9:30 am) with the stored default", () => {
    const maker = defaultMakerAt(new Date(2026, 9, 16, 9, 29));
    expect(maker).toBe("Scott");
    expect(defaultDrinkFor(maker, STORED)).toBe("americano");
  });
});
