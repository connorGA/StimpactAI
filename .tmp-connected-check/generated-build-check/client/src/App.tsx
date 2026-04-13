import { Switch, Route } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useState } from "react";
import Header from "@/components/Header";
import Explore from "@/pages/Explore";
import Library from "@/pages/Library";
import Leaderboard from "@/pages/Leaderboard";
import Admin from "@/pages/Admin";
import Create from "@/pages/Create";
import Profile from "@/pages/Profile";
import Playlists from "@/pages/Playlists";
import PlaylistDetail from "@/pages/PlaylistDetail";
import CategoryView from "@/pages/CategoryView";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import PaymentSuccess from "@/pages/PaymentSuccess";
import PurchaseCreditsDialog from "@/components/PurchaseCreditsDialog";
import MusicPlayerBar from "@/components/MusicPlayerBar";
import { MusicPlayerProvider } from "@/contexts/MusicPlayerContext";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { creditsService } from "@/lib/creditsService";
import NotFound from "@/pages/not-found";

function Router() {
  return (
    <Switch>
      <Route path="/" component={Explore} />
      <Route path="/library" component={Library} />
      <Route path="/leaderboard" component={Leaderboard} />
      <Route path="/admin" component={Admin} />
      <Route path="/create" component={Create} />
      <Route path="/profile" component={Profile} />
      <Route path="/playlists/:id" component={PlaylistDetail} />
      <Route path="/playlists" component={Playlists} />
      <Route path="/explore/:category" component={CategoryView} />
      <Route path="/login" component={Login} />
      <Route path="/signup" component={Signup} />
      <Route path="/payment/success" component={PaymentSuccess} />
      <Route path="/payment-success" component={PaymentSuccess} />
      <Route component={NotFound} />
    </Switch>
  );
}

function AppContent() {
  const { user } = useAuth();
  const [purchaseDialogOpen, setPurchaseDialogOpen] = useState(false);
  const [purchaseDialogTab, setPurchaseDialogTab] = useState<'credits' | 'subscriptions'>('credits');

  // Fetch user's credits (webhook creates initial record on subscription/purchase)
  useQuery({
    queryKey: ['/credits', user?.id],
    queryFn: async () => {
      if (!user) return null;

      try {
        // Fetch existing credits (created by webhook or previous purchases)
        const credits = await creditsService.getCurrentUser();
        return credits || null;
      } catch (error) {
        console.error("Error fetching credits:", error);
        return null;
      }
    },
    enabled: !!user,
    staleTime: 1000, // Keep credits fresh for 1 second
    refetchOnMount: true,
  });

  const handleOpenCredits = () => {
    setPurchaseDialogTab('credits');
    setPurchaseDialogOpen(true);
  };

  const handleOpenUpgrade = () => {
    setPurchaseDialogTab('subscriptions');
    setPurchaseDialogOpen(true);
  };

  return (
    <MusicPlayerProvider>
      <div className="min-h-screen bg-background pb-24">
        <Header
          onBuyCredits={handleOpenCredits}
          onUpgrade={handleOpenUpgrade}
        />
        <Router />
        <PurchaseCreditsDialog
          open={purchaseDialogOpen}
          onOpenChange={setPurchaseDialogOpen}
          defaultTab={purchaseDialogTab}
        />
        <MusicPlayerBar />
      </div>
      <Toaster />
    </MusicPlayerProvider>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;