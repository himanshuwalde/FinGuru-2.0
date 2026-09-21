import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { StatCard } from "@/components/ui/StatCard";

describe("StatCard", () => {
  it("renders the label and value", () => {
    render(<StatCard label="Net worth" value="₹12,40,500" delta={2.4} deltaLabel="vs last month" />);
    expect(screen.getByText("Net worth")).toBeTruthy();
    expect(screen.getByText("₹12,40,500")).toBeTruthy();
  });

  it("renders a rising-spend delta as a loss when spending more is bad", () => {
    render(<StatCard label="Monthly spend" value="₹38,210" delta={5.1} positiveIsGood={false} />);
    expect(screen.getByText(/5\.1%/)).toBeTruthy();
  });
});
