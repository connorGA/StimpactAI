import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import SubscriptionPlanCard from "./SubscriptionPlanCard";
import CreditPackageCard from "./CreditPackageCard";
import { usePlanLimits } from "@/hooks/usePlanLimits";
import { CREDIT_PACKAGES } from "@shared/schema";
import { Coins, Crown } from "lucide-react";

interface PurchaseCreditsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultTab?: 'credits' | 'subscriptions';
}

export default function PurchaseCreditsDialog({
  open,
  onOpenChange,
  defaultTab = 'credits',
}: PurchaseCreditsDialogProps) {
  const { planTier } = usePlanLimits();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] sm:max-w-[600px] lg:max-w-[1100px] max-h-[90vh] overflow-y-auto p-3 sm:p-6">
        <DialogHeader>
          <DialogTitle className="text-base sm:text-lg">Get Credits & Unlock Features</DialogTitle>
          <DialogDescription className="text-xs sm:text-sm">
            Purchase credit packages or subscribe for monthly credits and exclusive features
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue={defaultTab} className="mt-2 sm:mt-4">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="credits" data-testid="tab-credit-packages" className="text-xs sm:text-sm">
              <Coins className="h-3 w-3 sm:h-4 sm:w-4 mr-1 sm:mr-2" />
              Credits
            </TabsTrigger>
            <TabsTrigger value="subscriptions" data-testid="tab-subscriptions" className="text-xs sm:text-sm">
              <Crown className="h-3 w-3 sm:h-4 sm:w-4 mr-1 sm:mr-2" />
              Subscriptions
            </TabsTrigger>
          </TabsList>

          <TabsContent value="credits" className="mt-4 sm:mt-6">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4 pt-2">
              {CREDIT_PACKAGES.map((pkg) => (
                <CreditPackageCard
                  key={pkg.id}
                  package={pkg}
                />
              ))}
            </div>
            <p className="text-xs sm:text-sm text-muted-foreground text-center mt-4 sm:mt-6">
              One-time purchase • Credits never expire
            </p>
          </TabsContent>

          <TabsContent value="subscriptions" className="mt-4 sm:mt-6">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4 pt-2">
              <SubscriptionPlanCard
                planTier="plus"
                price={4.99}
                recommended={planTier === 'free'}
                currentPlan={planTier === 'plus'}
                monthlyCredits={200}
                features={[
                  "Everything in Free",
                  "Unlimited saved tracks",
                  "Create up to 3 playlists",
                  "200 credits per month",
                  "Vote on song requests"
                ]}
              />
              <SubscriptionPlanCard
                planTier="premium"
                price={9.99}
                recommended={planTier === 'plus'}
                currentPlan={planTier === 'premium'}
                monthlyCredits={1000}
                features={[
                  "Everything in Plus",
                  "Unlimited saved tracks",
                  "Unlimited playlists",
                  "1,000 credits per month"
                ]}
              />
              <SubscriptionPlanCard
                planTier="platinum"
                price={19.99}
                currentPlan={planTier === 'platinum'}
                monthlyCredits={3000}
                features={[
                  "Everything in Premium",
                  "Unlimited saved tracks",
                  "Unlimited playlists",
                  "3,000 credits per month"
                ]}
              />
            </div>
            <p className="text-xs sm:text-sm text-muted-foreground text-center mt-4 sm:mt-6">
              Recurring monthly subscription • Cancel anytime
            </p>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
