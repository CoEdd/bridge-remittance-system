"use client";

import clsx from "clsx";
import {
  BookCheck,
  FileText,
  House,
  MessageSquare,
  ScrollText,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Home", icon: House },
  { href: "/assistant", label: "Assistant", icon: MessageSquare },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/payees", label: "Payees", icon: Users },
  { href: "/sources", label: "Rule sources", icon: BookCheck },
  { href: "/audit", label: "Audit log", icon: ScrollText },
  { href: "/security", label: "Security", icon: ShieldCheck },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-line bg-surface">
      <div className="flex h-24 items-center px-6">
        <Link href="/" className="rounded-sm font-heading text-24 font-bold text-ink">
          Bridge
        </Link>
      </div>
      <nav aria-label="Main" className="px-3">
        <ul className="flex flex-col gap-1">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={clsx(
                    "relative flex h-10 items-center gap-3 rounded-control px-4 text-15 transition-colors duration-150",
                    active
                      ? "bg-teal-tint font-semibold text-ink"
                      : "text-body hover:bg-paper hover:text-ink",
                  )}
                >
                  {active && (
                    <span aria-hidden className="absolute inset-y-2 left-0 w-1 rounded-full bg-teal" />
                  )}
                  <Icon
                    aria-hidden
                    className={clsx("size-5", active ? "text-teal" : "text-muted")}
                    strokeWidth={1.75}
                  />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
