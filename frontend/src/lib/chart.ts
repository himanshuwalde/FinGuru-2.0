export const CHART_COLORS = {
  accent: "#22C55E",
  accentHover: "#16A34A",
  danger: "#EF4444",
  info: "#38BDF8",
  edge: "#223029",
  muted: "#8FA39C",
  ink: "#EAF2EF",
  surface: "#131A19",
} as const;

export interface GradientStop {
  offset: string;
  color: string;
  opacity: number;
}

export const GAIN_GRADIENT_STOPS: readonly GradientStop[] = [
  { offset: "0%", color: CHART_COLORS.accent, opacity: 0.35 },
  { offset: "100%", color: CHART_COLORS.accent, opacity: 0 },
];

export const LOSS_GRADIENT_STOPS: readonly GradientStop[] = [
  { offset: "0%", color: CHART_COLORS.danger, opacity: 0.35 },
  { offset: "100%", color: CHART_COLORS.danger, opacity: 0 },
];
