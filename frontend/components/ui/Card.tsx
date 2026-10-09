import clsx from "clsx";
import type { ReactNode } from "react";

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Card({ title, children, className }: CardProps) {
  return (
    <div className={clsx("rounded-card border border-line bg-surface p-6", className)}>
      {title && <h2 className="mb-4 font-heading text-18 font-semibold text-ink">{title}</h2>}
      {children}
    </div>
  );
}
