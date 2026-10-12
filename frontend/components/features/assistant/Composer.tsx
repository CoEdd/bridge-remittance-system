"use client";

import { Plus, Send } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Menu, type MenuItem } from "@/components/ui/Menu";

const UPLOAD = "upload";
const PASTE = "paste";

interface ComposerProps {
  /** True while Bridge is working: nothing can be sent. */
  disabled: boolean;
  onSend: (text: string) => void;
  onUpload: (file: File) => void;
  onPaste: () => void;
  demoItems: MenuItem[];
  onDemo: (key: string) => void;
  /** Lets "Upload an invoice" elsewhere on the screen open the same file chooser. */
  fileInput: React.RefObject<HTMLInputElement | null>;
}

/** Where the student types. "Add" holds the three ways to bring in a document. */
export function Composer({ disabled, onSend, onUpload, onPaste, demoItems, onDemo, fileInput }: ComposerProps) {
  const [text, setText] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);

  function send() {
    const message = text.trim();
    if (!message || disabled) return;
    onSend(message);
    setText("");
    field.current?.focus();
  }

  function add(key: string) {
    if (key === UPLOAD) fileInput.current?.click();
    else if (key === PASTE) onPaste();
    else onDemo(key);
  }

  return (
    <div className="flex items-end gap-2 border-t border-line p-3">
      <input
        ref={fileInput}
        type="file"
        accept=".pdf,.txt,image/*"
        aria-label="Choose a document to upload"
        className="sr-only"
        tabIndex={-1}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onUpload(file);
        }}
      />
      <Menu
        label="Add"
        icon={Plus}
        placement="above"
        disabled={disabled}
        items={[
          { key: UPLOAD, label: "Upload a file" },
          { key: PASTE, label: "Paste a message" },
          ...demoItems.map((item) => ({ ...item, label: `Demo: ${item.label}` })),
        ]}
        onSelect={add}
      />
      <label htmlFor="chat-message" className="sr-only">
        Message to Bridge
      </label>
      <textarea
        id="chat-message"
        ref={field}
        value={text}
        rows={1}
        maxLength={2000}
        disabled={disabled}
        placeholder="Ask Bridge"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          // Enter sends; Shift+Enter adds a new line. Enter while choosing Chinese characters does neither.
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            send();
          }
        }}
        className="max-h-28 min-h-10 flex-1 resize-none rounded-control border border-line bg-surface px-3 py-2 text-15 text-ink [field-sizing:content] placeholder:text-muted disabled:cursor-not-allowed disabled:bg-paper"
      />
      <Button icon={Send} disabled={disabled || !text.trim()} onClick={send}>
        Send
      </Button>
    </div>
  );
}
