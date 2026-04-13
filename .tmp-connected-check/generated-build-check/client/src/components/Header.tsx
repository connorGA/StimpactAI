import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Music,
  Coins,
  ShoppingCart,
  User,
  LogIn,
  UserPlus,
  ListMusic,
  Compass,
  LogOut,
  Heart,
  CreditCard,
} from "lucide-react";
import { Link, useLocation } from "wouter";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { creditsService } from "@/lib/creditsService";
import { usePlanLimits } from "@/hooks/usePlanLimits";
import { Crown } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import type { AccountStatus } from "@shared/schema";

interface HeaderProps {
  onBuyCredits?: () => void;
  onUpgrade?: () => void;
}

export default function Header({ onBuyCredits, onUpgrade }: HeaderProps) {
  const [location, navigate] = useLocation();
  const { user, isAuthenticated, logout } = useAuth();
  const { planTier } = usePlanLimits();
  const { toast } = useToast();

  const isAdmin = planTier === "admin";

  // Fetch user's credits
  const { data: userCredits } = useQuery({
    queryKey: ['/credits', user?.id],
    queryFn: () => user ? creditsService.getCurrentUser() : null,
    enabled: !!user,
  });

  // Fetch user's account status to check for subscription
  const { data: accountStatus, isError: accountStatusError } = useQuery<AccountStatus>({
    queryKey: ["/api/account-status", user?.id],
    enabled: !!user,
    retry: 1,
    staleTime: 60000, // Cache for 1 minute
  });

  const getPlanLabel = (tier: string) => {
    return tier.charAt(0).toUpperCase() + tier.slice(1);
  };

  const getPlanColor = (tier: string) => {
    switch (tier) {
      case "free":
        return "bg-gray-500/10 text-gray-500 border-gray-500/20";
      case "plus":
        return "bg-blue-500/10 text-blue-500 border-blue-500/20";
      case "premium":
        return "bg-purple-500/10 text-purple-500 border-purple-500/20";
      case "platinum":
        return "bg-amber-500/10 text-amber-500 border-amber-500/20";
      case "admin":
        return "bg-red-500/10 text-red-500 border-red-500/20";
      default:
        return "bg-gray-500/10 text-gray-500 border-gray-500/20";
    }
  };

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const handleBillingPortal = () => {
    // Direct link to Stripe Customer Portal (live mode)
    const portalUrl = 'https://billing.stripe.com/p/login/28E9AV8cs6Fw2Oy7iyeIw00';
    window.open(portalUrl, '_blank');
  };

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-xl">
      <div className="w-full">
        <div className="flex h-16 items-center justify-between gap-2 sm:gap-4">
          <Link
            href="/"
            className="flex items-center cursor-pointer pl-2 sm:pl-4"
            data-testid="link-home"
          >
            <img
              src="/synthetic-soul-logo.png"
              alt="Synthetic Soul"
              className="h-32 sm:h-36 md:h-42 w-auto object-contain"
            />
          </Link>

          <nav className="hidden md:flex absolute left-1/2 -translate-x-1/2 items-center gap-2">
            <Link href="/">
              <Button
                variant={location === "/" ? "secondary" : "ghost"}
                size="sm"
                data-testid="link-explore"
              >
                Explore
              </Button>
            </Link>
            <Link href="/library">
              <Button
                variant={location === "/library" ? "secondary" : "ghost"}
                size="sm"
                className="gap-1.5"
                data-testid="link-library"
              >
                <Heart className="h-4 w-4" />
                <span>Library</span>
              </Button>
            </Link>
            <Link href="/playlists">
              <Button
                variant={location === "/playlists" ? "secondary" : "ghost"}
                size="sm"
                className="gap-1.5"
                data-testid="link-playlists"
              >
                <ListMusic className="h-4 w-4" />
                <span>Playlists</span>
              </Button>
            </Link>
            <Link href="/leaderboard">
              <Button
                variant={location === "/leaderboard" ? "secondary" : "ghost"}
                size="sm"
                data-testid="link-leaderboard"
              >
                Requests
              </Button>
            </Link>
            {isAdmin && (
              <Link href="/create">
                <Button
                  variant={location === "/create" ? "secondary" : "ghost"}
                  size="sm"
                  data-testid="link-create"
                >
                  Create
                </Button>
              </Link>
            )}
          </nav>

          <div className="flex items-center gap-1.5 sm:gap-3 pr-2 sm:pr-4">
            {isAuthenticated && (
              <>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge
                      className={`gap-1.5 px-2 sm:px-3 py-1.5 hover-elevate cursor-default ${getPlanColor(planTier)}`}
                      data-testid="text-plan-tier"
                    >
                      <Crown className="h-3.5 w-3.5" />
                      <span className="font-semibold text-xs uppercase hidden sm:inline">
                        {getPlanLabel(planTier)}
                      </span>
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Your current plan: {getPlanLabel(planTier)}</p>
                  </TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge
                      className="gap-1.5 bg-primary/10 text-primary border-primary/20 px-2 sm:px-3 py-1.5 hover-elevate cursor-pointer active-elevate-2"
                      data-testid="button-credits"
                      onClick={onBuyCredits}
                    >
                      <Coins className="h-4 w-4" />
                      <span className="font-mono font-semibold">
                        {userCredits?.credits || 0}
                      </span>
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Click to purchase credits</p>
                  </TooltipContent>
                </Tooltip>
                <Button
                  size="sm"
                  className="gap-2"
                  onClick={onUpgrade}
                  data-testid="button-buy-credits"
                >
                  <Crown className="h-4 w-4" />
                  <span className="hidden sm:inline">Upgrade</span>
                </Button>
              </>
            )}

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                {isAuthenticated ? (
                  <Button
                    variant="ghost"
                    className="gap-2 rounded-full pl-2 pr-4 hover:bg-primary/10"
                    data-testid="button-profile-menu"
                  >
                    <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center border-2 border-primary">
                      <User className="h-4 w-4 text-primary" />
                    </div>
                    <span className="font-medium text-sm hidden sm:inline">
                      {user?.name || user?.username}
                    </span>
                  </Button>
                ) : (
                  <Button
                    size="icon"
                    variant="ghost"
                    className="rounded-full"
                    data-testid="button-profile-menu"
                  >
                    <User className="h-5 w-5" />
                  </Button>
                )}
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                {isAuthenticated ? (
                  <>
                    <div
                      className="px-2 py-1.5 text-sm font-medium"
                      data-testid="text-username"
                    >
                      {user?.name || user?.username}
                    </div>
                    <div className="px-2 py-1.5">
                      <Badge
                        className={`gap-1.5 px-2 py-1 text-xs ${getPlanColor(planTier)}`}
                        data-testid="text-plan-tier-menu"
                      >
                        <Crown className="h-3 w-3" />
                        <span className="font-semibold uppercase">
                          {getPlanLabel(planTier)} Plan
                        </span>
                      </Badge>
                    </div>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => navigate("/profile")}
                      data-testid="menu-item-profile"
                    >
                      <User className="h-4 w-4 mr-2" />
                      Profile
                    </DropdownMenuItem>
                    {(accountStatus?.stripe_customer_id || (accountStatusError && planTier !== 'free' && planTier !== 'admin')) && (
                      <DropdownMenuItem
                        onClick={handleBillingPortal}
                        data-testid="menu-item-billing"
                      >
                        <CreditCard className="h-4 w-4 mr-2" />
                        Billing
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => navigate("/")}
                      data-testid="menu-item-explore"
                    >
                      <Compass className="h-4 w-4 mr-2" />
                      Explore
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => navigate("/library")}
                      data-testid="menu-item-library"
                    >
                      <Heart className="h-4 w-4 mr-2" />
                      Library
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => navigate("/playlists")}
                      data-testid="menu-item-playlists"
                    >
                      <ListMusic className="h-4 w-4 mr-2" />
                      Playlists
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => navigate("/leaderboard")}
                      data-testid="menu-item-requests"
                    >
                      <ShoppingCart className="h-4 w-4 mr-2" />
                      Requests
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={handleLogout}
                      data-testid="menu-item-logout"
                    >
                      <LogOut className="h-4 w-4 mr-2" />
                      Sign Out
                    </DropdownMenuItem>
                  </>
                ) : (
                  <>
                    <DropdownMenuItem
                      onClick={() => navigate("/login")}
                      data-testid="menu-item-login"
                    >
                      <LogIn className="h-4 w-4 mr-2" />
                      Log In
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => navigate("/signup")}
                      data-testid="menu-item-signup"
                    >
                      <UserPlus className="h-4 w-4 mr-2" />
                      Sign Up
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>
    </header>
  );
}