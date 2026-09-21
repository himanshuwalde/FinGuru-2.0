import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { LandingPage } from "@/pages/landing/LandingPage";

describe("LandingPage", () => {
  it("renders the hero, all five pillars, and the differentiators", () => {
    render(<LandingPage />);

    expect(
      screen.getByRole("heading", { level: 1, name: /your financial command center/i }),
    ).toBeTruthy();

    for (const pillar of ["Track", "Grow", "Learn", "Protect", "AI CFO"]) {
      expect(screen.getByRole("heading", { name: new RegExp(`^${pillar}$`) })).toBeTruthy();
    }

    expect(screen.getByText("Every number is explainable")).toBeTruthy();
  });

  it("shows both Enter FinGuru CTAs (hero and final)", () => {
    render(<LandingPage />);
    expect(screen.getAllByRole("button", { name: "Enter FinGuru" }).length).toBe(2);
  });
});
