import { Link } from "react-router-dom";
import { PageHeader } from "@/components/ui/PageHeader";

export function NotFoundPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <PageHeader title="Page not found" description="This address does not match any screen." />
      <Link to="/" className="text-sm font-medium text-primary">
        Back to Home
      </Link>
    </div>
  );
}
