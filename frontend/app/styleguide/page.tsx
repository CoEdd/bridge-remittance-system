import { BadgeCheck, FileText, Upload } from "lucide-react";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { PageHeader } from "@/components/features/shell/PageHeader";
import { SheetDemo, TooltipDemo } from "@/components/features/styleguide/InteractiveDemos";
import { Amount } from "@/components/ui/Amount";
import { Badge, TierBadge, type Tier } from "@/components/ui/Badge";
import { Button, type ButtonSize, type ButtonVariant } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDate, formatTimestampUtc } from "@/lib/format";
import type { Currency } from "@/lib/types";

export const metadata: Metadata = { title: "Style guide" };

const COLOURS: { name: string; hex: string; swatch: string; use: string }[] = [
  { name: "ink", hex: "#0F1E2E", swatch: "bg-ink", use: "Headings, strong text" },
  { name: "paper", hex: "#F6F4EE", swatch: "bg-paper", use: "Page background" },
  { name: "surface", hex: "#FFFFFC", swatch: "bg-surface", use: "Cards" },
  { name: "line", hex: "#DDD9CC", swatch: "bg-line", use: "Borders" },
  { name: "body", hex: "#4A5568", swatch: "bg-body", use: "Body text" },
  { name: "muted", hex: "#5A6573", swatch: "bg-muted", use: "Secondary text" },
  { name: "teal", hex: "#12806F", swatch: "bg-teal", use: "Buttons, links, accents" },
  { name: "teal-bright", hex: "#2BB3A3", swatch: "bg-teal-bright", use: "Only on dark" },
  { name: "teal-tint", hex: "#E3F3EF", swatch: "bg-teal-tint", use: "Selected, success" },
  { name: "amber-line", hex: "#D98A1F", swatch: "bg-amber-line", use: "Approval borders" },
  { name: "amber-ink", hex: "#8A4B00", swatch: "bg-amber-ink", use: "Approval text" },
  { name: "amber-tint", hex: "#FBEBDD", swatch: "bg-amber-tint", use: "Approval background" },
  { name: "danger", hex: "#A1261B", swatch: "bg-danger", use: "Blocked text" },
  { name: "danger-tint", hex: "#FBE4E1", swatch: "bg-danger-tint", use: "Blocked background" },
];

const TYPE_SCALE: { label: string; className: string }[] = [
  { label: "32 px, Space Grotesk bold", className: "font-heading text-32 font-bold text-ink" },
  { label: "24 px, Space Grotesk semibold", className: "font-heading text-24 font-semibold text-ink" },
  { label: "18 px, Space Grotesk semibold", className: "font-heading text-18 font-semibold text-ink" },
  { label: "15 px, IBM Plex Sans", className: "text-15 text-body" },
  { label: "13 px, IBM Plex Sans", className: "text-13 text-muted" },
];

const VARIANTS: ButtonVariant[] = ["primary", "secondary", "ghost", "danger"];
const SIZES: ButtonSize[] = ["md", "lg"];
const VARIANT_LABELS: Record<ButtonVariant, string> = {
  primary: "Pay bill",
  secondary: "Cancel",
  ghost: "Show English",
  danger: "Block payee",
};

const TIERS: Tier[] = ["T0", "T1", "T2", "T3", "Blocked"];

const AMOUNTS: { minor: number; currency: Currency }[] = [
  { minor: 1200000, currency: "CNY" },
  { minor: 985000, currency: "MYR" },
  { minor: 18000, currency: "USD" },
  { minor: 9800, currency: "CNY" },
  { minor: 0, currency: "CNY" },
  { minor: -290000, currency: "CNY" },
  { minor: 123456789012, currency: "MYR" },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-8">
      <Card title={title}>{children}</Card>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-4 border-t border-line py-4 first:border-t-0 first:pt-0 last:pb-0">
      <span className="w-40 shrink-0 text-13 text-muted">{label}</span>
      <div className="flex flex-wrap items-center gap-4">{children}</div>
    </div>
  );
}

export default function StyleguidePage() {
  return (
    <>
      <PageHeader
        title="Style guide"
        description="Every UI component and state, for design review. Sample content only."
      />

      <Section title="Colours">
        <ul className="grid grid-cols-4 gap-4">
          {COLOURS.map(({ name, hex, swatch, use }) => (
            <li key={name} className="flex items-center gap-3">
              <span aria-hidden className={`size-10 shrink-0 rounded-control border border-line ${swatch}`} />
              <span className="flex flex-col">
                <span className="text-15 font-medium text-ink">{name}</span>
                <span className="text-13 text-muted">
                  {hex} · {use}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Type scale">
        {TYPE_SCALE.map(({ label, className }) => (
          <Row key={label} label={label}>
            <span className={className}>Bayar yuran CNY 12,000.00 sebelum 15 Nov 2026</span>
          </Row>
        ))}
      </Section>

      <Section title="Button">
        {SIZES.map((size) => (
          <Row key={size} label={`Size ${size}`}>
            {VARIANTS.map((variant) => (
              <Button key={variant} variant={variant} size={size}>
                {VARIANT_LABELS[variant]}
              </Button>
            ))}
          </Row>
        ))}
        <Row label="With icon">
          <Button icon={Upload}>Upload document</Button>
          <Button variant="secondary" icon={Upload} size="lg">
            Upload document
          </Button>
        </Row>
        <Row label="Loading">
          {VARIANTS.map((variant) => (
            <Button key={variant} variant={variant} loading>
              {VARIANT_LABELS[variant]}
            </Button>
          ))}
        </Row>
        <Row label="Disabled">
          {VARIANTS.map((variant) => (
            <Button key={variant} variant={variant} disabled>
              {VARIANT_LABELS[variant]}
            </Button>
          ))}
        </Row>
      </Section>

      <Section title="Badge">
        <Row label="Tones">
          <Badge>Neutral</Badge>
          <Badge tone="success" icon={BadgeCheck}>
            Verified
          </Badge>
          <Badge tone="warning">Needs approval</Badge>
          <Badge tone="danger">Contradicted</Badge>
        </Row>
        <Row label="Tiers">
          {TIERS.map((tier) => (
            <TierBadge key={tier} tier={tier} />
          ))}
        </Row>
      </Section>

      <Section title="Amount">
        <Row label="Tabular numerals">
          <ul className="flex flex-col items-end gap-1">
            {AMOUNTS.map(({ minor, currency }) => (
              <li key={`${currency}${minor}`}>
                <Amount minor={minor} currency={currency} className="text-18 text-ink" />
              </li>
            ))}
          </ul>
        </Row>
        <Row label="Sizes">
          <Amount minor={1200000} currency="CNY" className="text-32 font-bold text-ink" />
          <Amount minor={1200000} currency="CNY" className="text-24 font-semibold text-ink" />
          <Amount minor={1200000} currency="CNY" className="text-15 text-body" />
        </Row>
        <Row label="Dates">
          <span className="text-15 text-body">{formatDate("2026-11-15")}</span>
          <span className="text-15 text-body">{formatTimestampUtc("2026-10-09T03:15:42Z")}</span>
        </Row>
      </Section>

      <Section title="Card">
        <div className="grid grid-cols-2 gap-4">
          <Card title="Card with a title">
            <p className="text-15 text-body">Surface background, 1 px border, 12 px radius.</p>
          </Card>
          <Card>
            <p className="text-15 text-body">Card without a title.</p>
          </Card>
        </div>
      </Section>

      <Section title="EmptyState">
        <EmptyState
          icon={FileText}
          message="No documents have been uploaded yet."
          action={<Button icon={Upload}>Upload document</Button>}
        />
      </Section>

      <Section title="Skeleton">
        <div role="status" className="flex flex-col gap-3">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
          <span className="sr-only">Loading sample content</span>
        </div>
      </Section>

      <Section title="Tooltip">
        <TooltipDemo />
      </Section>

      <Section title="Sheet">
        <SheetDemo />
      </Section>
    </>
  );
}
