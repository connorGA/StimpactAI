import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { requestService } from "@/lib/requestService";
import { creditsService } from "@/lib/creditsService";
import { queryClient } from "@/lib/queryClient";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { usePlanLimits } from "@/hooks/usePlanLimits";
import LeaderboardCard from "@/components/LeaderboardCard";
import RequestSongDialog from "@/components/RequestSongDialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Trophy, Loader2, ChevronLeft, ChevronRight, Info, Sparkles, Crown, AlertCircle } from "lucide-react";
import { AnimatePresence } from "framer-motion";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import PurchaseCreditsDialog from "@/components/PurchaseCreditsDialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ToastAction } from "@/components/ui/toast";

const ITEMS_PER_PAGE = 10;
const GOAL_VOTES = 30;
const REQUEST_COST = 200;

export default function Leaderboard() {
  const { user } = useAuth();
  const { toast } = useToast();
  const { limits, getUpgradeMessage, planTier } = usePlanLimits();
  const [currentPage, setCurrentPage] = useState(1);
  const [votingId, setVotingId] = useState<string | null>(null);
  const [upgradeDialogOpen, setUpgradeDialogOpen] = useState(false);

  // Fetch all requests
  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['/requests'],
    queryFn: () => requestService.getAll(),
  });

  // Fetch user's credits
  const { data: userCredits } = useQuery({
    queryKey: ['/credits', user?.id],
    queryFn: () => user ? creditsService.getCurrentUser() : null,
    enabled: !!user,
  });

  // Sort requests by votes (descending)
  const sortedRequests = [...requests]
    .filter(req => !req.released)
    .sort((a, b) => b.votes - a.votes);

  const totalVotes = sortedRequests.reduce((sum, req) => sum + req.votes, 0);
  const queuedCount = sortedRequests.filter(req => req.votes >= GOAL_VOTES).length;
  
  // Pagination
  const totalPages = Math.ceil(sortedRequests.length / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const paginatedRequests = sortedRequests.slice(startIndex, endIndex);

  // Upvote mutation
  const upvoteMutation = useMutation({
    mutationFn: async ({ requestId, currentVotes }: { requestId: string; currentVotes: number }) => {
      if (!user) throw new Error("User not authenticated");
      if (!userCredits) throw new Error("Could not load user credits");
      
      const originalCredits = userCredits.credits;
      
      try {
        // Deduct 10 credits from user first
        await creditsService.deduct(userCredits.id, 10, userCredits.credits);
        
        // Then update the request votes
        const updatedRequest = await requestService.update(requestId, {
          votes: currentVotes + 1,
          requests_id: requestId,
        });
        
        return updatedRequest;
      } catch (error) {
        // Rollback credits if vote update failed
        try {
          await creditsService.update(userCredits.id, {
            credits: originalCredits,
            credits_id: userCredits.id,
          });
        } catch (rollbackError) {
          console.error("Failed to rollback credits:", rollbackError);
        }
        throw error;
      }
    },
    onMutate: async ({ requestId }) => {
      // Optimistically update credits in the UI
      if (user && userCredits) {
        queryClient.setQueryData(['/credits', user.id], {
          ...userCredits,
          credits: userCredits.credits - 10,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/requests'] });
      queryClient.invalidateQueries({ queryKey: ['/credits', user?.id] });
      setVotingId(null);
      toast({
        title: "Vote added!",
        description: "Your vote has been counted. 10 credits deducted.",
      });
    },
    onError: (error: Error) => {
      queryClient.invalidateQueries({ queryKey: ['/credits', user?.id] });
      setVotingId(null);
      toast({
        title: "Failed to vote",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Create request mutation
  const createRequestMutation = useMutation({
    mutationFn: async (data: { title: string; artist: string; genre: string; description?: string }) => {
      if (!user) throw new Error("User not authenticated");
      if (!userCredits) throw new Error("Could not load user credits");
      
      const originalCredits = userCredits.credits;
      
      try {
        // Deduct REQUEST_COST credits from user first
        await creditsService.deduct(userCredits.id, REQUEST_COST, userCredits.credits);
        
        // Then create the request
        const newRequest = await requestService.create({
          title: data.title,
          artist: data.artist,
          genre: data.genre,
          description: data.description || '',
          votes: 0,
          released: false,
        });
        
        return newRequest;
      } catch (error) {
        // Rollback credits if request creation failed
        try {
          await creditsService.update(userCredits.id, {
            credits: originalCredits,
            credits_id: userCredits.id,
          });
        } catch (rollbackError) {
          console.error("Failed to rollback credits:", rollbackError);
        }
        throw error;
      }
    },
    onMutate: async () => {
      // Optimistically update credits in the UI
      if (user && userCredits) {
        queryClient.setQueryData(['/credits', user.id], {
          ...userCredits,
          credits: userCredits.credits - REQUEST_COST,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/requests'] });
      queryClient.invalidateQueries({ queryKey: ['/credits', user?.id] });
      toast({
        title: "Request created!",
        description: `Your song request has been submitted. ${REQUEST_COST} credits deducted.`,
      });
    },
    onError: (error: Error) => {
      queryClient.invalidateQueries({ queryKey: ['/credits', user?.id] });
      toast({
        title: "Failed to create request",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handleVote = (id: string) => {
    if (!user) {
      toast({
        title: "Authentication required",
        description: "Please log in to vote on requests.",
        variant: "destructive",
      });
      return;
    }

    // Check if user's plan allows upvoting
    if (!limits.canUpvote) {
      const upgradeMsg = getUpgradeMessage('upvotes');
      toast({
        title: "Feature not available",
        description: upgradeMsg || "Upgrade your plan to participate in voting",
        variant: "destructive",
      });
      return;
    }

    // Check if user has sufficient credits
    if (!userCredits || userCredits.credits < 10) {
      toast({
        title: "Insufficient credits",
        description: "Purchase additional credits to vote",
        action: (
          <ToastAction 
            altText="View credits" 
            onClick={() => setUpgradeDialogOpen(true)}
            data-testid="button-view-credits-toast"
          >
            View Credits
          </ToastAction>
        ),
      });
      return;
    }

    const request = requests.find(r => r.id === id);
    if (request) {
      setVotingId(id);
      upvoteMutation.mutate({ requestId: id, currentVotes: request.votes });
    }
  };

  const handleSubmitRequest = (songName: string, artistName: string, genre: string) => {
    if (!user) {
      toast({
        title: "Authentication required",
        description: "Please log in to submit requests.",
        variant: "destructive",
      });
      return;
    }

    // Check if user's plan allows song requests
    if (!limits.canRequestSongs) {
      const upgradeMsg = getUpgradeMessage('requests');
      toast({
        title: "Feature not available",
        description: upgradeMsg || "Upgrade your plan to submit song requests",
        variant: "destructive",
      });
      return;
    }

    if (!userCredits || userCredits.credits < REQUEST_COST) {
      setUpgradeDialogOpen(true);
      return;
    }

    // Check for duplicate
    const existingRequest = requests.find(
      (req) => 
        req.title.toLowerCase() === songName.toLowerCase() &&
        req.artist.toLowerCase() === artistName.toLowerCase()
    );

    if (existingRequest) {
      toast({
        title: "Duplicate request",
        description: "This request has already been made, please up vote the existing request to get it to you sooner!",
        variant: "destructive",
      });
      return;
    }

    createRequestMutation.mutate({
      title: songName,
      artist: artistName,
      genre: genre,
    });
  };

  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-muted-foreground">Loading requests...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-3 sm:px-6 py-4 sm:py-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-0 mb-4 sm:mb-6">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                  <Trophy className="h-6 w-6 text-primary" />
                </div>
                <div>
                  <h1 className="text-2xl sm:text-3xl font-bold text-foreground">Requests</h1>
                  <p className="text-xs sm:text-sm text-muted-foreground">
                    {sortedRequests.length} {sortedRequests.length === 1 ? 'request' : 'requests'} • {totalVotes} total votes
                    {queuedCount > 0 && (
                      <span className="inline-flex items-center gap-1 ml-2">
                        • <Sparkles className="h-3 w-3 text-primary" /> {queuedCount} queued
                      </span>
                    )}
                  </p>
                </div>
              </div>
            </div>
            {planTier === 'free' ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <div>
                    <RequestSongDialog
                      onSubmit={handleSubmitRequest}
                      userCredits={userCredits?.credits || 0}
                      requestCost={REQUEST_COST}
                    />
                  </div>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-xs">
                  <p className="text-sm">Upgrade to Plus, Premium, or Platinum to request AI-generated songs</p>
                </TooltipContent>
              </Tooltip>
            ) : (
              <RequestSongDialog
                onSubmit={handleSubmitRequest}
                userCredits={userCredits?.credits || 0}
                requestCost={REQUEST_COST}
                onUpgradeClick={() => setUpgradeDialogOpen(true)}
              />
            )}
          </div>

          {/* Info Banner */}
          <div className="mb-2 sm:mb-8 rounded-lg border border-primary/20 bg-primary/5 p-2 sm:p-4">
            <div className="flex items-start gap-1.5 sm:gap-3">
              <Info className="h-4 w-4 sm:h-5 sm:w-5 text-primary mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-xs sm:text-sm font-medium text-foreground mb-0.5 sm:mb-1">
                  How It Works
                </p>
                <p className="text-[11px] sm:text-sm text-muted-foreground">
                  Request for <span className="font-semibold text-foreground">{REQUEST_COST} credits</span>. 
                  Reach <span className="font-semibold text-foreground">{GOAL_VOTES} votes</span> to get created. 
                  Vote with <span className="font-semibold text-foreground">10 credits</span>!
                </p>
              </div>
            </div>
          </div>

          {/* Upgrade Banner for Free Users */}
          {planTier === 'free' && (
            <Alert className="mb-8 border-primary/20 bg-primary/5" data-testid="alert-upgrade-requests">
              <AlertCircle className="h-5 w-5 text-primary" />
              <AlertTitle className="text-foreground font-semibold">Upgrade to Participate in Requests</AlertTitle>
              <AlertDescription className="text-muted-foreground">
                You're on the Free plan, which doesn't include credits for song requests or voting. 
                Upgrade to Plus ($4.99/month) for 100 monthly credits, Premium ($9.99/month) for 1,000 credits, or Platinum ($19.99/month) for 3,000 credits.
                <div className="mt-3">
                  <Button 
                    size="sm" 
                    className="gap-2"
                    onClick={() => setUpgradeDialogOpen(true)}
                    data-testid="button-upgrade-from-requests-banner"
                  >
                    <Crown className="h-4 w-4" />
                    View Plans
                  </Button>
                </div>
              </AlertDescription>
            </Alert>
          )}

          {sortedRequests.length > 0 ? (
            <>
              <div className="space-y-2 sm:space-y-4 mb-8">
                <AnimatePresence mode="popLayout">
                  {paginatedRequests.map((request, index) => (
                    <LeaderboardCard
                      key={request.id}
                      id={request.id}
                      title={`${request.title} - ${request.artist}`}
                      description={`Genre: ${request.genre}`}
                      votes={request.votes}
                      rank={startIndex + index + 1}
                      totalVotes={totalVotes}
                      hasVoteCredits={userCredits ? userCredits.credits >= 10 : false}
                      onVote={handleVote}
                      isVoting={votingId === request.id}
                      goalVotes={GOAL_VOTES}
                      planTier={planTier}
                    />
                  ))}
                </AnimatePresence>
              </div>

              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-1 sm:gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handlePageChange(currentPage - 1)}
                    disabled={currentPage === 1}
                    data-testid="button-previous-page"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  
                  <div className="flex items-center gap-0.5 sm:gap-1">
                    {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => {
                      // Show first page, last page, current page, and pages around current
                      const showPage = 
                        page === 1 || 
                        page === totalPages || 
                        Math.abs(page - currentPage) <= 1;
                      
                      const showEllipsis = 
                        (page === currentPage - 2 && currentPage > 3) ||
                        (page === currentPage + 2 && currentPage < totalPages - 2);

                      if (showEllipsis) {
                        return <span key={page} className="px-1 sm:px-2 text-muted-foreground text-xs sm:text-sm">...</span>;
                      }

                      if (!showPage) return null;

                      return (
                        <Button
                          key={page}
                          variant={currentPage === page ? "default" : "ghost"}
                          size="sm"
                          onClick={() => handlePageChange(page)}
                          className="min-w-[2rem] sm:min-w-[2.5rem] h-8 sm:h-9 text-xs sm:text-sm"
                          data-testid={`button-page-${page}`}
                        >
                          {page}
                        </Button>
                      );
                    })}
                  </div>

                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handlePageChange(currentPage + 1)}
                    disabled={currentPage === totalPages}
                    data-testid="button-next-page"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="rounded-full bg-muted p-6 mb-4">
                <Trophy className="h-10 w-10 text-muted-foreground" />
              </div>
              <h2 className="text-xl font-semibold text-foreground mb-2">No requests yet</h2>
              <p className="text-muted-foreground mb-6">Be the first to request a song!</p>
            </div>
          )}

          <PurchaseCreditsDialog
            open={upgradeDialogOpen}
            onOpenChange={setUpgradeDialogOpen}
          />
        </div>
      </div>
    </div>
  );
}
