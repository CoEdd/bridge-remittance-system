"use client";

import { ChevronDown, type LucideIcon } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import clsx from "clsx";
import { Button, type ButtonSize, type ButtonVariant } from "./Button";

export interface MenuItem {
  key: string;
  label: string;
  /** A short second line, such as a file name. */
  hint?: string;
}

interface MenuProps {
  label: string;
  icon?: LucideIcon;
  items: MenuItem[];
  onSelect: (key: string) => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Where the list opens: under the button, or above it when the button sits at the bottom of the screen. */
  placement?: "below" | "above";
}

/** A button that opens a short list of choices. Esc or a click outside closes it. */
export function Menu({
  label,
  icon,
  items,
  onSelect,
  loading = false,
  disabled = false,
  variant = "secondary",
  size = "md",
  placement = "below",
}: MenuProps) {
  const menuId = useId();
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        container.current?.querySelector("button")?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={container} className="relative">
      <Button
        variant={variant}
        size={size}
        icon={icon}
        loading={loading}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen(!open)}
      >
        {label}
        <ChevronDown aria-hidden className="size-4" />
      </Button>
      {open && (
        <ul
          id={menuId}
          role="menu"
          aria-label={label}
          className={clsx(
            "absolute z-40 w-72 rounded-card border border-line bg-surface p-1 shadow-overlay",
            placement === "above" ? "bottom-full left-0 mb-2" : "right-0 mt-2",
          )}
        >
          {items.map((item) => (
            <li key={item.key} role="none">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onSelect(item.key);
                }}
                className="flex w-full flex-col rounded-control px-3 py-2 text-left transition-colors duration-150 hover:bg-teal-tint"
              >
                <span className="text-15 text-ink">{item.label}</span>
                {item.hint && <span className="text-13 text-muted">{item.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
