import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Check, Sparkles } from "lucide-react";

interface CreditsPurchaseCardProps {
  credits: number;
  price: number;
  recommended?: boolean;
  onPurchase?: (credits: number) => void;
}

export default function CreditsPurchaseCard({
  credits,
  price,
  recommended = false,
  onPurchase,
}: CreditsPurchaseCardProps) {
  return (
    <Card
      className={`relative overflow-hidden hover-elevate transition-all duration-200 ${
        recommended ? "border-primary shadow-lg shadow-primary/20" : ""
      }`}
    >
      {recommended && (
        <Badge className="absolute top-4 right-4 bg-primary text-primary-foreground gap-1">
          <Sparkles className="h-3 w-3" />
          Most Popular
        </Badge>
      )}
      <div className="p-6">
        <div className="mb-4">
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-bold text-foreground">
              {credits}
            </span>
            <span className="text-muted-foreground">credits</span>
          </div>
        </div>

        <div className="mb-6">
          <div className="flex items-baseline gap-1">
            <span className="text-3xl font-bold text-foreground">
              ${price.toFixed(2)}
            </span>
            <span className="text-muted-foreground">USD</span>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            ${(price / credits).toFixed(3)} per credit
          </p>
        </div>

        <Button
          className="w-full"
          variant={recommended ? "default" : "outline"}
          onClick={() => onPurchase?.(credits)}
          data-testid={`button-purchase-${credits}`}
        >
          Purchase Credits
        </Button>

        <div className="mt-4 space-y-2">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Check className="h-4 w-4 text-primary" />
            <span>Instant delivery</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Check className="h-4 w-4 text-primary" />
            <span>Secure checkout</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Check className="h-4 w-4 text-primary" />
            <span>Never expires</span>
          </div>
        </div>
      </div>
    </Card>
  );
}
