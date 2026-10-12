import { ArrowRight } from "lucide-react";
import { Fragment } from "react";
import { Card } from "@/components/ui/Card";
import { formatDate } from "@/lib/format";
import type { ClaimCheckOverview, EvalNumbers } from "@/lib/types";

const STAGES = [
  { title: "Message", note: "Any wording, any language" },
  { title: "Neural", note: "The LLM extracts claims" },
  { title: "Symbolic", note: "Facts and rules judge them" },
  { title: "Verdict", note: "With its reasoning chain" },
];

function share(part: number, whole: number): string {
  return `${part} / ${whole}`;
}

function Numbers({ label, numbers, strong }: { label: string; numbers: EvalNumbers; strong: boolean }) {
  return (
    <tr className={strong ? "font-semibold text-ink" : "text-body"}>
      <th scope="row" className="py-1 pr-6 text-left text-15 font-[inherit]">
        {label}
      </th>
      <td className="py-1 pr-6 font-heading text-15 tabular-nums">{share(numbers.caught, numbers.scams)}</td>
      <td className="py-1 font-heading text-15 tabular-nums">{share(numbers.false_blocks, numbers.legit)}</td>
    </tr>
  );
}

/**
 * The neuro-symbolic claim check in brief: how it works, what it measured, and its rules.
 * The name always sits next to what it does and the measured result.
 */
export function ClaimCheckCard({ overview }: { overview: ClaimCheckOverview }) {
  const result = overview.evaluation;
  return (
    <Card title="Neuro-symbolic claim check">
      <ol className="flex items-stretch gap-2">
        {STAGES.map((stage, index) => (
          <Fragment key={stage.title}>
            {index > 0 && <ArrowRight aria-hidden className="size-5 shrink-0 self-center text-muted" />}
            <li className="flex-1 rounded-control border border-line bg-paper px-3 py-2">
              <p className="text-15 font-semibold text-ink">{stage.title}</p>
              <p className="text-13 text-body">{stage.note}</p>
            </li>
          </Fragment>
        ))}
      </ol>

      {result ? (
        <div className="mt-4">
          <table>
            <caption className="sr-only">Measured results on the test set</caption>
            <thead>
              <tr className="text-13 text-muted">
                <td />
                <th scope="col" className="pr-6 pb-1 text-left font-medium">
                  Scams caught
                </th>
                <th scope="col" className="pb-1 text-left font-medium">
                  Blocked by mistake
                </th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.arms).map(([arm, label]) => (
                <Numbers key={arm} label={label} numbers={result.overall[arm]} strong={arm === "C"} />
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-13 text-muted" title={result.caveat}>
            Test set of {result.items} messages · {result.model} · {formatDate(result.date)}
          </p>
        </div>
      ) : (
        <p className="mt-4 text-15 text-body">Not measured yet. Run make eval-claims.</p>
      )}

      <details className="mt-3">
        <summary className="cursor-pointer rounded-sm text-13 font-medium text-teal">
          The {overview.rules.length} rules
        </summary>
        <ol className="mt-2 flex flex-col gap-1">
          {overview.rules.map((rule) => (
            <li key={rule.id} className="text-13 text-body">
              <span className="font-medium text-ink">
                {rule.id} · {rule.title.en}.
              </span>{" "}
              {rule.text.en}
            </li>
          ))}
        </ol>
      </details>
    </Card>
  );
}
