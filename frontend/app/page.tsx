import { RecentActivity } from "@/components/features/home/RecentActivity";
import { SpendingCard } from "@/components/features/home/SpendingCard";
import { UpcomingBills } from "@/components/features/home/UpcomingBills";
import { WalletCards } from "@/components/features/home/WalletCards";
import { PageHeader } from "@/components/features/shell/PageHeader";

export default function HomePage() {
  return (
    <>
      <PageHeader title="Home" description="Wallets, upcoming bills and recent activity." />
      <WalletCards />
      <div className="mt-6 grid grid-cols-12 gap-6">
        <div className="col-span-7">
          <SpendingCard />
        </div>
        <div className="col-span-5">
          <UpcomingBills />
        </div>
      </div>
      <div className="mt-6">
        <RecentActivity />
      </div>
    </>
  );
}
