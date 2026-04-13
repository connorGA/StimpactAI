import { useEffect } from "react";
import { Link } from "wouter";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CheckCircle, ArrowRight } from "lucide-react";
import { queryClient } from "@/lib/queryClient";
import { useAuth } from "@/contexts/AuthContext";

export default function PaymentSuccess() {
  const { user } = useAuth();

  useEffect(() => {
    // Invalidate queries to fetch updated credits and account status
    if (user?.id) {
      queryClient.invalidateQueries({ queryKey: ['/credits', user.id] });
      queryClient.invalidateQueries({ queryKey: ['/account_status', user.id] });
    }
  }, [user?.id]);

  return (
    <div className="container mx-auto px-4 py-8 flex items-center justify-center min-h-[80vh]">
      <Card className="max-w-md w-full">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
            <CheckCircle className="h-10 w-10 text-primary" />
          </div>
          <CardTitle className="text-2xl">Payment Successful!</CardTitle>
          <CardDescription>
            Your purchase has been completed successfully
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-center space-y-2">
            <p className="text-sm text-muted-foreground">
              Your credits and subscription status have been updated. 
              You can now enjoy all the features of your plan!
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Button asChild data-testid="button-go-to-home">
              <Link href="/">
                Back to Home
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
