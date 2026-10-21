import { useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigation } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { ADMIN_NAV, USER_NAV, type NavItem } from "@/app/layouts/nav";
import { cn } from "@/lib/cn";

export function AppLayout() {
  const { pathname } = useLocation();
  const navigation = useNavigation();
  const admin = pathname.startsWith("/admin");
  const items = admin ? ADMIN_NAV : USER_NAV;
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <div className="min-h-screen bg-paper text-ink">
      {navigation.state === "loading" ? (
        <div
          className="fixed inset-x-0 top-0 z-50 h-0.5 animate-pulse bg-primary"
          role="progressbar"
          aria-label="Loading"
        />
      ) : null}
      <div className="flex min-h-screen">
        {/* Sticky and viewport-high, so the workspace switch stays visible on long pages. */}
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-surface lg:flex">
          <Brand className="px-4 py-5" />
          <NavList items={items} className="min-h-0 flex-1 overflow-y-auto px-3 py-2" />
          <ModeSwitch admin={admin} />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-line bg-surface px-4 py-3 lg:hidden">
            <Brand />
            <button
              type="button"
              className="inline-flex size-11 items-center justify-center rounded-xl border border-line"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              onClick={() => setOpen((value) => !value)}
            >
              {open ? <X className="size-5" /> : <Menu className="size-5" />}
            </button>
          </header>
          {open ? (
            <div className="border-b border-line bg-surface px-3 py-3 lg:hidden">
              <NavList items={items} onNavigate={close} />
              <ModeSwitch admin={admin} onNavigate={close} />
            </div>
          ) : null}
          <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}

function NavList({ items, className, onNavigate }: { items: NavItem[]; className?: string; onNavigate?: () => void }) {
  return (
    <nav className={cn("flex flex-col gap-1", className)}>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium",
              isActive ? "bg-primary-soft text-primary" : "text-ink hover:bg-paper",
            )
          }
        >
          <item.icon className="size-4 shrink-0" aria-hidden="true" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

function Brand({ className }: { className?: string }) {
  return (
    <Link to="/" className={cn("flex items-center gap-2", className)}>
      <span className="grid size-8 place-items-center rounded-lg bg-primary text-sm font-semibold text-primary-ink">
        Q
      </span>
      <span className="text-base font-semibold tracking-tight">QueryMind</span>
    </Link>
  );
}

function ModeSwitch({ admin, onNavigate }: { admin: boolean; onNavigate?: () => void }) {
  return (
    <div className="border-t border-line p-3">
      <p className="px-3 pb-2 text-xs font-medium tracking-wide text-muted uppercase">Workspace</p>
      <Link
        to={admin ? "/" : "/admin"}
        onClick={onNavigate}
        className="flex min-h-11 items-center rounded-xl px-3 text-sm font-medium text-primary hover:bg-primary-soft"
      >
        {admin ? "Analyst view" : "Admin console"}
      </Link>
    </div>
  );
}
