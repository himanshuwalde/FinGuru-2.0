import {
  BarChart3,
  Bot,
  Briefcase,
  Calculator,
  Copy,
  CreditCard,
  Flame,
  Gauge,
  Ghost,
  GraduationCap,
  Landmark,
  LayoutDashboard,
  Lock,
  Percent,
  Radar,
  Receipt,
  Shield,
  ShieldCheck,
  ShoppingBasket,
  TrendingUp,
  Trophy,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Track",
    items: [
      { to: "/track", label: "Dashboard", icon: LayoutDashboard },
      { to: "/track/transactions", label: "Transactions & Budgeting", icon: Receipt },
      { to: "/track/safe-to-spend", label: "Safe-to-Spend", icon: Gauge },
      { to: "/track/anomalies", label: "Anomaly Finder", icon: Radar },
      { to: "/track/ghost-spend", label: "Ghost Spend Auditor", icon: Ghost },
      { to: "/track/accounts", label: "Account Aggregator", icon: Landmark },
      { to: "/track/net-worth", label: "Net Worth Tracker", icon: TrendingUp },
    ],
  },
  {
    label: "Grow",
    items: [
      { to: "/grow/portfolio", label: "Portfolio Tracker", icon: Briefcase },
      { to: "/grow/fire", label: "FIRE Planner", icon: Flame },
      { to: "/grow/financial-twin", label: "Financial Twin", icon: Copy },
      { to: "/grow/tax", label: "Tax Planner", icon: Percent },
      { to: "/grow/trust-engine", label: "Trust Engine", icon: ShieldCheck },
      { to: "/grow/calculators", label: "Calculators Hub", icon: Calculator },
      { to: "/grow/card-optimizer", label: "Card Rewards Optimizer", icon: CreditCard },
      { to: "/grow/mutual-funds", label: "Mutual Fund Explorer", icon: BarChart3 },
      { to: "/grow/fd", label: "FD Discovery", icon: Landmark },
      { to: "/grow/baskets", label: "Basket Explorer", icon: ShoppingBasket },
    ],
  },
  {
    label: "Learn",
    items: [
      { to: "/learn/lessons", label: "Money School", icon: GraduationCap },
      { to: "/learn/leaderboard", label: "Leaderboard", icon: Trophy },
    ],
  },
  {
    label: "Protect",
    items: [
      { to: "/protect/insurance", label: "Insurance Advisor", icon: ShieldCheck },
      { to: "/protect/guardrail", label: "Financial Guardrail", icon: Shield },
      { to: "/protect/family-legacy", label: "Family & Legacy", icon: Users },
      { to: "/protect/web3-vault", label: "Web3 Vault", icon: Lock },
    ],
  },
  {
    label: "AI CFO",
    items: [{ to: "/ai-cfo", label: "Chat", icon: Bot }],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((group) => group.items);
