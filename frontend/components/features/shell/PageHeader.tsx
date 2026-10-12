import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description: string;
  /** One shortcut shown at the right, for example a link to a section further down the page. */
  action?: ReactNode;
}

export function PageHeader({ title, description, action }: PageHeaderProps) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <div>
        <h1 className="font-heading text-32 font-bold text-ink">{title}</h1>
        <p className="mt-1 text-15 text-body">{description}</p>
      </div>
      {action}
    </div>
  );
}
