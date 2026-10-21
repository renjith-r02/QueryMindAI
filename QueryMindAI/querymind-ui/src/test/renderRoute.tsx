import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { routes } from "@/app/routes";

let shimmed = false;

/** jsdom gaps the data router and Recharts need; installed once per test file. */
function installShims() {
  if (shimmed) return;
  shimmed = true;
  // React Router builds a Node `Request` with jsdom's AbortSignal, which Node rejects.
  // Dropping the signal is fine in tests; nothing here relies on aborting navigations.
  const NodeRequest = globalThis.Request;
  globalThis.Request = class extends NodeRequest {
    constructor(input: RequestInfo | URL, init: RequestInit = {}) {
      super(input, { ...init, signal: undefined });
    }
  };
  // Recharts' ResponsiveContainer needs ResizeObserver, which jsdom lacks.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

/** Render the app's real routes at `path`, inside the layout. */
export function renderRoute(path: string) {
  installShims();
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}
