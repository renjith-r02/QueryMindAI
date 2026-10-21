import {
  Clock,
  Database,
  Home,
  KeyRound,
  LayoutDashboard,
  LayoutGrid,
  MessageCircle,
  ScrollText,
  Settings,
  Shield,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";

export type NavItem = { to: string; label: string; icon: LucideIcon; end?: boolean };

/** Sidebar entries. Add a route in app/routes.tsx and its label here. */
export const USER_NAV: NavItem[] = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/ask", label: "Ask Question", icon: MessageCircle },
  { to: "/history", label: "History", icon: Clock },
  { to: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { to: "/settings", label: "Settings", icon: SlidersHorizontal },
];

export const ADMIN_NAV: NavItem[] = [
  { to: "/admin", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/admin/schema", label: "Schema", icon: Database },
  { to: "/admin/logs", label: "Logs", icon: ScrollText },
  { to: "/admin/guardrails", label: "Guardrails", icon: Shield },
  { to: "/admin/model", label: "Model Config", icon: Settings },
  { to: "/admin/okta", label: "Okta SSO", icon: KeyRound },
];
