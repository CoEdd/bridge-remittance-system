"use client";

import { Info, PanelRightOpen } from "lucide-react";
import { useState } from "react";
import { Amount } from "@/components/ui/Amount";
import { TierBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import { Tooltip } from "@/components/ui/Tooltip";

export function TooltipDemo() {
  return (
    <Tooltip label="Shown on hover and on keyboard focus">
      <Button variant="secondary" icon={Info}>
        Hover or focus me
      </Button>
    </Tooltip>
  );
}

export function SheetDemo() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button variant="secondary" icon={PanelRightOpen} onClick={() => setOpen(true)}>
        Open sheet
      </Button>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title="Sample sheet"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => setOpen(false)}>Confirm</Button>
          </>
        }
      >
        <p className="text-15 text-body">
          Sample content for review. Tab stays inside the sheet, Esc closes it, and focus returns
          to the button that opened it.
        </p>
        <dl className="mt-6 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <dt className="text-13 text-muted">Sample amount</dt>
            <dd>
              <Amount minor={1200000} currency="CNY" className="text-18 font-semibold text-ink" />
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-13 text-muted">Sample tier</dt>
            <dd>
              <TierBadge tier="T3" />
            </dd>
          </div>
        </dl>
      </Sheet>
    </>
  );
}
