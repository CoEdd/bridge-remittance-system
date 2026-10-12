"use client";

import { Loadable } from "@/components/features/home/Loadable";
import { Amount } from "@/components/ui/Amount";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatTimestampUtc } from "@/lib/format";
import type { Account, Currency, Rate } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const CURRENCY_NAMES: Record<Currency, string> = {
  MYR: "Malaysian ringgit",
  CNY: "Chinese yuan",
  USD: "US dollar",
};

/** Where the rate comes from and when it was fetched: shown on hover, not on the card. */
function rateSource(rate: Rate): string {
  return rate.source === "frankfurter"
    ? `ECB via Frankfurter, ${formatTimestampUtc(rate.fetched_at)}`
    : "Offline snapshot";
}

function WalletCard({ account, home }: { account: Account; home: Currency }) {
  return (
    <Card className="flex h-full flex-col">
      <h2 className="text-15 font-medium whitespace-nowrap text-ink">
        {account.currency}
        <span className="ml-2 font-normal text-muted">{CURRENCY_NAMES[account.currency]}</span>
      </h2>
      <Amount
        minor={account.balance_minor}
        currency={account.currency}
        className="mt-3 block text-32 font-bold text-ink"
      />
      {account.rate ? (
        <>
          <p className="mt-1 text-15 text-body">
            About <Amount minor={account.home_equivalent_minor} currency={home} />
          </p>
          <p className="mt-auto pt-4 text-13 text-muted" title={rateSource(account.rate)}>
            1 {account.rate.base} = {account.rate.mid_rate} {account.rate.quote} ·{" "}
            {account.rate.source === "frankfurter" ? "ECB" : "offline"}
          </p>
        </>
      ) : (
        <p className="mt-1">
          <Badge>Home currency</Badge>
        </p>
      )}
    </Card>
  );
}

export function WalletCards() {
  const result = useApi(api.accounts);

  return (
    <section aria-label="Wallets">
      <Loadable
        result={result}
        loadingLabel="Loading wallets"
        loading={
          <div className="grid grid-cols-3 gap-4">
            {[0, 1, 2].map((key) => (
              <Card key={key}>
                <Skeleton className="h-6 w-32" />
                <Skeleton className="mt-3 h-10 w-56" />
                <Skeleton className="mt-3 h-5 w-40" />
              </Card>
            ))}
          </div>
        }
      >
        {(data) => (
          <ul className="grid grid-cols-3 gap-4">
            {data.accounts.map((account) => (
              <li key={account.id}>
                <WalletCard account={account} home={data.home_currency} />
              </li>
            ))}
          </ul>
        )}
      </Loadable>
    </section>
  );
}
