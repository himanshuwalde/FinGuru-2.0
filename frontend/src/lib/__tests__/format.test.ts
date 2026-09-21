import { describe, expect, it } from "vitest";

import { formatINR, formatMonthLabel, greetingFor } from "@/lib/format";

describe("format helpers", () => {
  it("formats rupees with Indian digit grouping", () => {
    expect(formatINR(1240500)).toBe("₹12,40,500");
    expect(formatINR(38210)).toBe("₹38,210");
    expect(formatINR(0)).toBe("₹0");
  });

  it("shortens backend month labels for chart axes", () => {
    expect(formatMonthLabel("Apr 2026")).toBe("Apr");
  });

  it("maps local hours to greetings", () => {
    expect(greetingFor(8)).toBe("Good Morning");
    expect(greetingFor(14)).toBe("Good Afternoon");
    expect(greetingFor(20)).toBe("Good Evening");
  });
});
