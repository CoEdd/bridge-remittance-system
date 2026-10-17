"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";

interface PasteSheetProps {
  open: boolean;
  onClose: () => void;
  busy: boolean;
  /** Reads the pasted text as a message document, with its sender if given. Resolves to true when it worked. */
  onRead: (text: string, sender: string) => Promise<boolean>;
}

/** A text box for a payment message copied from a chat app or an email. */
export function PasteSheet({ open, onClose, busy, onRead }: PasteSheetProps) {
  const [message, setMessage] = useState("");
  const [sender, setSender] = useState("");

  async function read() {
    if (await onRead(message, sender)) {
      setMessage("");
      setSender("");
    }
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
      <label htmlFor="pasted-sender" className="mb-2 block text-13 font-medium text-muted">
        From (optional)
      </label>
      <input
        id="pasted-sender"
        value={sender}
        onChange={(event) => setSender(event.target.value)}
        maxLength={80}
        className="mb-4 h-10 w-full rounded-control border border-line bg-surface px-3 text-15 text-ink"
      />
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
