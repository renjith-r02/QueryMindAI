import { isRouteErrorResponse, Link, useRouteError } from "react-router-dom";

/** Shown when a route fails to render or its loader throws. */
export function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "Unknown error";

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4 px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Something went wrong</h1>
      <pre className="overflow-x-auto rounded-2xl border border-line bg-surface px-4 py-3 font-mono text-sm">
        {message}
      </pre>
      <div className="flex gap-3 text-sm font-medium">
        <button type="button" className="text-primary" onClick={() => window.location.reload()}>
          Reload
        </button>
        <Link to="/" className="text-primary">
          Go home
        </Link>
      </div>
    </div>
  );
}

export function PageLoader() {
  return <p className="px-4 py-8 text-center text-sm text-muted">Loading…</p>;
}
