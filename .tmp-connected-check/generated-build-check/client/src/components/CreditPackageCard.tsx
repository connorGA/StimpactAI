import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Coins, Sparkles } from "lucide-react";
import type { CreditPackage } from "@shared/schema";
import { useAuth } from "@/contexts/AuthContext";

interface CreditPackageCardProps {
  package: CreditPackage;
}

// Stripe Payment Links for credit packages
const PAYMENT_LINKS: Record<string, string> = {
  'starter': 'https://buy.stripe.com/6oUbJ3akAd3U2Oy0UaeIw03',
  'power': 'https://buy.stripe.com/aFa3cx78o8NE4WGdGWeIw04',
  'ultimate': 'https://buy.stripe.com/7sYbJ31O4fc23SC7iyeIw05',
};

export default function CreditPackageCard({ package: pkg }: CreditPackageCardProps) {
  const { user } = useAuth();

  const handlePurchase = () => {
    const paymentLink = PAYMENT_LINKS[pkg.id];
    
    if (!paymentLink) {
      console.error(`No payment link configured for package: ${pkg.id}`);
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
    <Card className="relative overflow-visible hover-elevate">
      {pkg.popular && (
        <Badge className="absolute -top-2 left-1/2 -translate-x-1/2 bg-primary text-primary-foreground gap-1 text-xs px-2 py-0.5 whitespace-nowrap">
          <Sparkles className="h-3 w-3" />
          Popular
        </Badge>
      )}
      <CardHeader className="p-3 sm:p-6 pt-4 sm:pt-6">
        <CardTitle className="flex items-center justify-between text-sm sm:text-base">
          <span className="flex items-center gap-1.5 sm:gap-2">
            <Coins className="h-4 w-4 sm:h-5 sm:w-5 text-primary" />
            <span>{pkg.name}</span>
          </span>
        </CardTitle>
        <CardDescription>
          <span className="text-2xl sm:text-3xl font-bold text-foreground">${pkg.price.toFixed(2)}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="p-3 sm:p-6 pt-0 sm:pt-0">
        <div className="space-y-1 sm:space-y-2">
          <div className="flex items-center justify-between py-1.5 sm:py-2 border-t">
            <span className="text-xs sm:text-sm text-muted-foreground">Credits</span>
            <span className="text-sm sm:text-lg font-semibold">{pkg.credits.toLocaleString()}</span>
          </div>
          <div className="flex items-center justify-between py-1.5 sm:py-2 border-t">
            <span className="text-xs sm:text-sm text-muted-foreground">Per credit</span>
            <span className="text-xs sm:text-sm font-medium">${(pkg.price / pkg.credits).toFixed(3)}</span>
          </div>
        </div>
      </CardContent>
      <CardFooter className="p-3 sm:p-6 pt-0 sm:pt-0">
        <Button
          onClick={handlePurchase}
          className="w-full"
          variant={pkg.popular ? "default" : "outline"}
          data-testid={`button-purchase-${pkg.id}`}
        >
          Buy Credits
        </Button>
      </CardFooter>
    </Card>
  );
}
