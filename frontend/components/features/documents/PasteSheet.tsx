"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";

interface PasteSheetProps {
  open: boolean;
  onClose: () => void;
  busy: boolean;
  /** Reads the pasted text as a message document. Resolves to true when it worked. */
  onRead: (text: string) => Promise<boolean>;
}

/** A text box for a payment message copied from a chat app or an email. */
export function PasteSheet({ open, onClose, busy, onRead }: PasteSheetProps) {
  const [message, setMessage] = useState("");

  async function read() {
    if (await onRead(message)) setMessage("");
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Paste a message"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={busy} disabled={!message.trim()} onClick={() => void read()}>
            Read message
          </Button>
        </>
      }
    >
      <label htmlFor="pasted-message" className="mb-2 block text-13 font-medium text-muted">
        Message
      </label>
      <textarea
        id="pasted-message"
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        rows={12}
        className="w-full rounded-control border border-line bg-surface p-3 text-15 text-ink"
      />
    </Sheet>
  );
}
