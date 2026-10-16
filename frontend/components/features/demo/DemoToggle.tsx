"use client";

import { Play } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useDemo } from "@/lib/demo";

/** The header's "Demo" button: shows or hides the presenter's demo bar (also the D key). */
export function DemoToggle() {
  const { visible, toggleVisible } = useDemo();
  return (
    <Button variant={visible ? "primary" : "secondary"} icon={Play} aria-pressed={visible} onClick={toggleVisible}>
      Demo
    </Button>
  );
}
