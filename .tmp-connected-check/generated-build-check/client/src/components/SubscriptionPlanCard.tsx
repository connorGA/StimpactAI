import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Check, Sparkles, Crown } from "lucide-react";
import type { PlanTier } from "@shared/schema";
import { useAuth } from "@/contexts/AuthContext";

interface SubscriptionPlanCardProps {
  planTier: PlanTier;
  price: number;
  recommended?: boolean;
  currentPlan?: boolean;
  features: string[];
  monthlyCredits: number;
}

const planIcons = {
  free: null,
  plus: <Sparkles className="h-5 w-5" />,
  premium: <Crown className="h-5 w-5" />,
  platinum: <Crown className="h-5 w-5" />,
  admin: <Crown className="h-5 w-5" />,
};

const planNames = {
  free: "Free",
  plus: "Plus",
  premium: "Premium",
  platinum: "Platinum",
  admin: "Admin",
};

// Stripe Payment Links for subscription plans
const SUBSCRIPTION_PAYMENT_LINKS: Record<string, string> = {
  'plus': 'https://buy.stripe.com/28E9AV8cs6Fw2Oy7iyeIw00',
  'premium': 'https://buy.stripe.com/8x28wR8cs5Bs4WG8mCeIw01',
  'platinum': 'https://buy.stripe.com/7sY7sN50g2pgdtc32ieIw02',
};

export default function SubscriptionPlanCard({
  planTier,
  price,
  recommended = false,
  currentPlan = false,
  features,
  monthlyCredits,
}: SubscriptionPlanCardProps) {
  const { user } = useAuth();

  const handleSubscribe = () => {
    if (planTier === 'free') {
      // No need to redirect for free plan
      return;
    }

    const paymentLink = SUBSCRIPTION_PAYMENT_LINKS[planTier];
    
    if (!paymentLink) {
      console.error(`No payment link configured for plan: ${planTier}`);
      return;
    }

    // Construct the payment link URL with prefilled email and client_reference_id
    const url = new URL(paymentLink);
    if (user?.email) {
      url.searchParams.set('prefilled_email', user.email);
    }
    if (user?.id) {
      url.searchParams.set('client_reference_id', user.id);
    }

    // Redirect to Stripe checkout
    window.location.href = url.toString();
  };

  return (
    <Card
      className={`relative overflow-visible hover-elevate transition-all duration-200 ${
        recommended ? "border-primary shadow-lg shadow-primary/20" : ""
      } ${currentPlan ? "border-2 border-primary" : ""}`}
      data-testid={`card-plan-${planTier}`}
    >
      {recommended && (
        <Badge className="absolute -top-2 left-1/2 -translate-x-1/2 bg-primary text-primary-foreground gap-1 text-xs px-2 py-0.5 whitespace-nowrap">
          <Sparkles className="h-3 w-3" />
          Popular
        </Badge>
      )}
      {currentPlan && (
        <Badge className="absolute -top-2 left-1/2 -translate-x-1/2 bg-primary text-primary-foreground gap-1 text-xs px-2 py-0.5 whitespace-nowrap">
          Current Plan
        </Badge>
      )}
      <div className="p-3 sm:p-6 pt-4 sm:pt-6">
        <div className="mb-3 sm:mb-4">
          <div className="flex items-center gap-1.5 sm:gap-2 mb-1.5 sm:mb-2">
            {planIcons[planTier] && (
              <div className="text-primary">{planIcons[planTier]}</div>
            )}
            <h3 className="text-base sm:text-2xl font-bold text-foreground">
              {planNames[planTier]}
            </h3>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl sm:text-4xl font-bold text-foreground">
              ${price.toFixed(2)}
            </span>
            <span className="text-sm sm:text-base text-muted-foreground">
              {price === 0 ? "" : "/mo"}
            </span>
          </div>
          {monthlyCredits > 0 && (
            <p className="text-xs sm:text-sm text-primary mt-1 sm:mt-2 font-medium">
              {monthlyCredits.toLocaleString()} credits per month
            </p>
          )}
        </div>

        <Button
          className="w-full mb-3 sm:mb-4"
          variant={currentPlan ? "secondary" : recommended ? "default" : "outline"}
          onClick={handleSubscribe}
          disabled={currentPlan}
          data-testid={`button-subscribe-${planTier}`}
        >
          {currentPlan ? "Current Plan" : planTier === 'free' ? "Continue Free" : "Subscribe"}
        </Button>

        <div className="space-y-1.5 sm:space-y-2">
          {features.map((feature, index) => (
            <div key={index} className="flex items-start gap-2 text-xs sm:text-sm">
              <Check className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-primary mt-0.5 flex-shrink-0" />
              <span className="text-muted-foreground leading-tight">{feature}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
