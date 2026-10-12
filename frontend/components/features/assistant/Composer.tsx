"use client";

import { ClipboardPaste, FolderOpen, Paperclip, Send } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Menu, type MenuItem } from "@/components/ui/Menu";

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

/** Where the student types, attaches a file, pastes a message or picks a demo document. */
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

  return (
    <div className="border-t border-line p-3">
      <div className="flex items-end gap-2">
        <label htmlFor="chat-message" className="sr-only">
          Message to Bridge
        </label>
        <textarea
          id="chat-message"
          ref={field}
          value={text}
          rows={2}
          maxLength={2000}
          disabled={disabled}
          placeholder="Ask about a bill or a payment request"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends; Shift+Enter adds a new line. Enter while choosing Chinese characters does neither.
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              send();
            }
          }}
          className="min-h-16 flex-1 resize-none rounded-control border border-line bg-surface px-3 py-2 text-15 text-ink placeholder:text-muted disabled:cursor-not-allowed disabled:bg-paper"
        />
        <Button icon={Send} disabled={disabled || !text.trim()} onClick={send}>
          Send
        </Button>
      </div>
      {/* Tighter buttons, so the three tools stay on one line in the 1440px layout. */}
      <div className="mt-1 flex flex-wrap items-center [&_button]:px-2">
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
        <Button variant="ghost" size="sm" icon={Paperclip} disabled={disabled} onClick={() => fileInput.current?.click()}>
          Attach
        </Button>
        <Button variant="ghost" size="sm" icon={ClipboardPaste} disabled={disabled} onClick={onPaste}>
          Paste a message
        </Button>
        <Menu
          label="Use a demo document"
          icon={FolderOpen}
          variant="ghost"
          size="sm"
          placement="above"
          disabled={disabled}
          items={demoItems}
          onSelect={onDemo}
        />
      </div>
    </div>
  );
}
