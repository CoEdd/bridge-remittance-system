"use client";

import { useEffect, useRef } from "react";

interface Range {
  start: number;
  end: number;
  kind: "active" | "hidden";
}

interface SourceTextProps {
  text: string;
  /** The source span of the field being hovered or focused. */
  active: { start: number; end: number } | null;
  /** Hidden text found in the document; it is marked wherever it appears. */
  hidden: string[];
}

/** The document's text, line breaks kept, with the active field's exact source highlighted. */
export function SourceText({ text, active, hidden }: SourceTextProps) {
  const box = useRef<HTMLPreElement>(null);
  const mark = useRef<HTMLElement>(null);

  // Bring the highlight into view inside the text box only; never move the page.
  useEffect(() => {
    const container = box.current;
    const target = mark.current;
    if (!container || !target) return;
    const top = target.offsetTop;
    const visible = top >= container.scrollTop && top + target.offsetHeight <= container.scrollTop + container.clientHeight;
    if (!visible) container.scrollTop = Math.max(0, top - container.clientHeight / 2);
  }, [active?.start, active?.end]);

  const ranges: Range[] = [];
  for (const piece of hidden) {
    const start = text.indexOf(piece);
    if (start >= 0) ranges.push({ start, end: start + piece.length, kind: "hidden" });
  }
  if (active && active.end > active.start) ranges.push({ ...active, kind: "active" });
  ranges.sort((a, b) => a.start - b.start);

  const parts = [];
  let position = 0;
  for (const range of ranges) {
    if (range.start < position) continue; // overlapping ranges: keep the first
    if (range.start > position) parts.push(<span key={position}>{text.slice(position, range.start)}</span>);
    const piece = text.slice(range.start, range.end);
    parts.push(
      range.kind === "active" ? (
        <mark
          key={range.start}
          ref={mark}
          className="rounded-sm bg-teal-tint text-ink underline decoration-teal decoration-2 underline-offset-4"
        >
          {piece}
        </mark>
      ) : (
        <span key={range.start} title="Hidden text" className="rounded-sm bg-danger-tint text-danger">
          {piece}
        </span>
      ),
    );
    position = range.end;
  }
  if (position < text.length) parts.push(<span key={position}>{text.slice(position)}</span>);

  return (
    <pre
      ref={box}
      tabIndex={0}
      aria-label="Original text"
      className="relative max-h-[560px] overflow-auto font-sans text-15 leading-7 break-words whitespace-pre-wrap text-ink"
    >
      {parts}
    </pre>
  );
}
