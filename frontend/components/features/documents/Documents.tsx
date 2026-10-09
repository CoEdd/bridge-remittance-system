"use client";

import clsx from "clsx";
import { ClipboardPaste, FileText, FolderOpen, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { DocumentView } from "@/components/features/documents/DocumentView";
import { KIND_LABELS, STATUS, languageList } from "@/components/features/documents/labels";
import { Loadable } from "@/components/features/home/Loadable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Menu } from "@/components/ui/Menu";
import { Sheet } from "@/components/ui/Sheet";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { DocumentDetail, DocumentSummary } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Busy = "upload" | "paste" | "demo" | null;

function DocumentList({
  documents,
  selected,
  onSelect,
}: {
  documents: DocumentSummary[];
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <ul className="flex flex-col gap-2">
      {documents.map((document) => {
        const status = STATUS[document.status];
        const current = document.id === selected;
        return (
          <li key={document.id}>
            <button
              type="button"
              aria-current={current ? "true" : undefined}
              onClick={() => onSelect(document.id)}
              className={clsx(
                "flex w-full flex-col gap-1 rounded-card border p-4 text-left transition-colors duration-150",
                current ? "border-teal bg-teal-tint" : "border-line bg-surface hover:bg-paper",
              )}
            >
              <span className="text-15 font-medium break-words text-ink">{document.filename}</span>
              <span className="text-13 text-muted">
                {KIND_LABELS[document.kind]} · {languageList(document.languages)}
              </span>
              <span className="mt-1 flex items-center justify-between gap-2">
                <Badge tone={status.tone}>{status.label}</Badge>
                <span className="text-13 text-muted">{formatDate(document.created_at.slice(0, 10))}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function Documents() {
  const fileInput = useRef<HTMLInputElement>(null);
  const list = useApi(api.documents);
  const demos = useApi(api.demoDocuments);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [pasting, setPasting] = useState(false);
  const [message, setMessage] = useState("");

  const loadDetail = useCallback(
    (signal: AbortSignal): Promise<DocumentDetail | null> =>
      selected === null ? Promise.resolve(null) : api.document(selected, signal),
    [selected],
  );
  const detail = useApi(loadDetail);

  // Open the newest document when the list first arrives.
  const newest = list.state.status === "ready" ? (list.state.data[0]?.id ?? null) : null;
  useEffect(() => {
    if (selected === null && newest !== null) setSelected(newest);
  }, [selected, newest]);

  async function ingest(kind: Exclude<Busy, null>, run: () => Promise<DocumentDetail>): Promise<boolean> {
    setBusy(kind);
    setError(null);
    try {
      const document = await run();
      setSelected(document.id);
      list.reload();
      return true;
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "The document could not be read.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function readMessage() {
    if (await ingest("paste", () => api.pasteMessage(message))) {
      setPasting(false);
      setMessage("");
    }
  }

  const demoItems =
    demos.state.status === "ready"
      ? demos.state.data.map((demo) => ({ key: demo.key, label: demo.label, hint: demo.filename }))
      : [];
  const upload = (
    <Button icon={Upload} loading={busy === "upload"} onClick={() => fileInput.current?.click()}>
      Upload document
    </Button>
  );

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-end gap-2">
        {error && (
          <p role="alert" className="mr-auto text-15 font-medium text-danger">
            {error}
          </p>
        )}
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.txt,image/*"
          aria-label="Choose a document to upload"
          className="sr-only"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void ingest("upload", () => api.uploadDocument(file));
          }}
        />
        {upload}
        <Button variant="secondary" icon={ClipboardPaste} onClick={() => setPasting(true)}>
          Paste a message
        </Button>
        <Menu
          label="Use a demo document"
          icon={FolderOpen}
          items={demoItems}
          loading={busy === "demo"}
          onSelect={(key) => void ingest("demo", () => api.ingestDemoDocument(key))}
        />
      </div>

      <Loadable
        result={list}
        loadingLabel="Loading documents"
        loading={
          <div className="grid grid-cols-[280px_1fr] gap-6">
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-96 w-full" />
          </div>
        }
      >
        {(documents) =>
          documents.length === 0 ? (
            <Card>
              <EmptyState icon={FileText} message="No documents yet." action={upload} />
            </Card>
          ) : (
            <div className="grid grid-cols-[280px_1fr] items-start gap-6">
              <DocumentList documents={documents} selected={selected} onSelect={setSelected} />
              <Loadable
                result={detail}
                loadingLabel="Loading the document"
                loading={<Skeleton className="h-96 w-full" />}
              >
                {(document) => (document ? <DocumentView key={document.id} document={document} /> : null)}
              </Loadable>
            </div>
          )
        }
      </Loadable>

      <Sheet
        open={pasting}
        onClose={() => setPasting(false)}
        title="Paste a message"
        footer={
          <>
            <Button variant="secondary" onClick={() => setPasting(false)}>
              Cancel
            </Button>
            <Button loading={busy === "paste"} disabled={!message.trim()} onClick={() => void readMessage()}>
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
    </>
  );
}
