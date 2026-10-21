import type { ComponentType } from "react";
import type { RouteObject } from "react-router-dom";
import { AppLayout } from "@/app/layouts/AppLayout";
import { PageLoader, RouteError } from "@/app/RouteError";

/**
 * Route modules are loaded on demand. Each page module exports its component
 * and, optionally, a `loader` that fetches the data it needs.
 */
type PageModule = { loader?: RouteObject["loader"] } & Record<string, unknown>;

function page(load: () => Promise<PageModule>, component: string): RouteObject["lazy"] {
  return async () => {
    const module = await load();
    return { Component: module[component] as ComponentType, loader: module.loader };
  };
}

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    errorElement: <RouteError />,
    hydrateFallbackElement: <PageLoader />,
    children: [
      {
        // Errors inside a page render within the layout, keeping the sidebar usable.
        errorElement: <RouteError />,
        children: [
          { index: true, lazy: page(() => import("@/pages/HomePage"), "HomePage") },
          { path: "ask", lazy: page(() => import("@/pages/AskPage"), "AskPage") },
          { path: "history", lazy: page(() => import("@/pages/HistoryPage"), "HistoryPage") },
          { path: "dashboard", lazy: page(() => import("@/pages/DashboardPage"), "DashboardPage") },
          { path: "settings", lazy: page(() => import("@/pages/SettingsPage"), "SettingsPage") },
          {
            path: "admin",
            children: [
              { index: true, lazy: page(() => import("@/pages/admin/OverviewPage"), "OverviewPage") },
              { path: "schema", lazy: page(() => import("@/pages/admin/SchemaPage"), "SchemaPage") },
              { path: "logs", lazy: page(() => import("@/pages/admin/LogsPage"), "LogsPage") },
              { path: "guardrails", lazy: page(() => import("@/pages/admin/GuardrailsPage"), "GuardrailsPage") },
              { path: "model", lazy: page(() => import("@/pages/admin/ModelPage"), "ModelPage") },
              { path: "okta", lazy: page(() => import("@/pages/admin/OktaPage"), "OktaPage") },
            ],
          },
          { path: "*", lazy: page(() => import("@/pages/NotFoundPage"), "NotFoundPage") },
        ],
      },
    ],
  },
];
