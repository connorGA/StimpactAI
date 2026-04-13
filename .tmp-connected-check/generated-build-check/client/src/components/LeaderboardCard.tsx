import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ChevronUp, Crown, Medal, Award, Sparkles, Clock } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface LeaderboardCardProps {
  id: string;
  rank: number;
  title: string;
  description: string;
  votes: number;
  totalVotes: number;
  onVote?: (id: string) => void;
  hasVoteCredits?: boolean;
  isVoting?: boolean;
  goalVotes?: number;
  planTier?: string;
}

export default function LeaderboardCard({
  id,
  rank,
  title,
  description,
  votes,
  totalVotes,
  onVote,
  hasVoteCredits = true,
  isVoting = false,
  goalVotes = 30,
  planTier,
}: LeaderboardCardProps) {
  const [justVoted, setJustVoted] = useState(false);
  const goalPercentage = Math.min((votes / goalVotes) * 100, 100);
  const communitySupportPercentage = Math.min((votes / goalVotes) * 100, 100);
  const isQueued = votes >= goalVotes;
  
  const getOrdinalSuffix = (n: number) => {
    const s = ["th", "st", "nd", "rd"];
    const v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  };

  const getRankIcon = () => {
    if (rank === 1) return <Crown className="h-5 w-5" />;
    if (rank === 2) return <Medal className="h-5 w-5" />;
    if (rank === 3) return <Award className="h-5 w-5" />;
    return null;
  };

  const getRankStyles = () => {
    if (rank === 1) return {
      badge: 'bg-gradient-to-br from-yellow-500/20 to-yellow-600/20 text-yellow-600 dark:text-yellow-400 border-yellow-500/40',
      glow: 'shadow-lg shadow-yellow-500/20',
      text: 'text-yellow-600 dark:text-yellow-400'
    };
    if (rank === 2) return {
      badge: 'bg-gradient-to-br from-slate-400/20 to-slate-500/20 text-slate-600 dark:text-slate-300 border-slate-400/40',
      glow: 'shadow-lg shadow-slate-400/20',
      text: 'text-slate-600 dark:text-slate-300'
    };
    if (rank === 3) return {
      badge: 'bg-gradient-to-br from-amber-600/20 to-amber-700/20 text-amber-700 dark:text-amber-500 border-amber-600/40',
      glow: 'shadow-lg shadow-amber-600/20',
      text: 'text-amber-700 dark:text-amber-500'
    };
    return {
      badge: 'bg-muted text-muted-foreground border-border',
      glow: '',
      text: 'text-muted-foreground'
    };
  };

  const styles = getRankStyles();

  const handleVote = () => {
    setJustVoted(true);
    onVote?.(id);
    setTimeout(() => setJustVoted(false), 600);
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
    >
      <Card className={`hover-elevate transition-all duration-200 ${rank <= 3 ? styles.glow : ''} ${isQueued ? 'border-primary/50' : ''}`}>
        {isQueued && (
          <div className="bg-gradient-to-r from-primary/10 via-chart-1/10 to-primary/10 border-b border-primary/20 px-3 py-1.5 sm:px-6 sm:py-3">
            <div className="flex items-center gap-1.5 sm:gap-2">
              <motion.div
                animate={{ rotate: [0, 10, -10, 0] }}
                transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
              >
                <Sparkles className="h-3 w-3 sm:h-4 sm:w-4 text-primary" />
              </motion.div>
              <span className="text-xs sm:text-sm font-semibold text-primary flex items-center gap-1.5 sm:gap-2">
                <Clock className="h-3 w-3 sm:h-4 sm:w-4" />
                <span className="hidden xs:inline">Queued for Creation</span>
                <span className="xs:hidden">Queued</span>
              </span>
              <Badge variant="secondary" className="ml-auto text-[10px] sm:text-xs">
                <span className="hidden xs:inline">Goal Reached!</span>
                <span className="xs:hidden">Goal!</span>
              </Badge>
            </div>
          </div>
        )}
        
        <div className="flex items-start gap-2 sm:gap-4 p-3 sm:p-6">
          <div className="flex-shrink-0 flex flex-col items-center gap-1 sm:gap-2">
            <Badge 
              className={`h-10 w-10 sm:h-12 sm:w-12 rounded-lg p-0 flex items-center justify-center ${styles.badge}`}
            >
              {rank <= 3 ? getRankIcon() : <span className="font-bold text-base sm:text-lg">{rank}</span>}
            </Badge>
            <span className={`text-[11px] sm:text-xs font-semibold ${styles.text}`}>
              {getOrdinalSuffix(rank)}
            </span>
          </div>
          
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-sm sm:text-lg text-foreground mb-0.5 sm:mb-1 line-clamp-1" data-testid={`text-request-title-${id}`}>
              {title}
            </h3>
            <p className="text-xs sm:text-sm text-muted-foreground mb-1.5 sm:mb-4 hidden sm:block" data-testid={`text-request-description-${id}`}>
              {description}
            </p>
            
            <div className="space-y-1 sm:space-y-3">
              {/* Goal Progress */}
              <div>
                <div className="flex items-center justify-between mb-0.5 sm:mb-2">
                  <span className="text-[11px] sm:text-xs font-medium text-muted-foreground">
                    <span className="hidden sm:inline">{isQueued ? 'Goal Complete' : 'Progress to Creation'}</span>
                    <span className="sm:hidden">Progress</span>
                  </span>
                  <span className="text-[11px] sm:text-xs font-mono text-muted-foreground">
                    {votes}/{goalVotes}
                  </span>
                </div>
                <div className="h-1.5 sm:h-2.5 w-full bg-secondary rounded-full overflow-hidden">
                  <motion.div
                    className={`h-full ${
                      isQueued 
                        ? 'bg-gradient-to-r from-primary via-chart-1 to-primary' 
                        : 'bg-gradient-to-r from-muted-foreground/40 to-muted-foreground/60'
                    }`}
                    initial={{ width: 0 }}
                    animate={{ width: `${goalPercentage}%` }}
                    transition={{ duration: 0.5, ease: "easeOut" }}
                  />
                </div>
              </div>

              {/* Community Support */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1 sm:gap-2">
                  <span className="text-[11px] sm:text-xs font-medium text-muted-foreground hidden sm:inline">
                    Community Support
                  </span>
                  <span className="text-[11px] sm:text-xs font-mono text-muted-foreground">{communitySupportPercentage.toFixed(1)}%</span>
                </div>
                
                <div className="flex items-center gap-2 sm:gap-3">
                  <div className="flex flex-col items-end">
                    <span className="text-[11px] sm:text-xs text-muted-foreground font-medium hidden sm:block">Total Votes</span>
                    <AnimatePresence mode="wait">
                      <motion.span 
                        key={votes}
                        initial={{ scale: justVoted ? 1.5 : 1, color: justVoted ? 'rgb(var(--primary))' : undefined }}
                        animate={{ scale: 1 }}
                        transition={{ duration: 0.3, ease: "easeOut" }}
                        className="font-mono text-lg sm:text-2xl font-bold text-foreground"
                        data-testid={`text-votes-${id}`}
                      >
                        {votes}
                      </motion.span>
                    </AnimatePresence>
                  </div>

                  {planTier === 'free' ? (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div>
                          <Button
                            variant="outline"
                            className="flex-shrink-0 h-9 w-9 sm:h-12 sm:w-12 p-0"
                            onClick={handleVote}
                            disabled={isVoting}
                            data-testid={`button-vote-${id}`}
                          >
                            <motion.div
                              animate={isVoting ? { y: [-2, 2, -2] } : {}}
                              transition={{ repeat: isVoting ? Infinity : 0, duration: 0.6 }}
                            >
                              <ChevronUp className="h-5 w-5 sm:h-6 sm:w-6" />
                            </motion.div>
                          </Button>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="left" className="max-w-xs">
                        <p className="text-sm">Upgrade to earn credits and vote on requests</p>
                      </TooltipContent>
                    </Tooltip>
                  ) : (
                    <Button
                      variant={hasVoteCredits ? "default" : "outline"}
                      className="flex-shrink-0 h-9 w-9 sm:h-12 sm:w-12 p-0"
                      onClick={handleVote}
                      disabled={isVoting}
                      data-testid={`button-vote-${id}`}
                    >
                      <motion.div
                        animate={isVoting ? { y: [-2, 2, -2] } : {}}
                        transition={{ repeat: isVoting ? Infinity : 0, duration: 0.6 }}
                      >
                        <ChevronUp className="h-5 w-5 sm:h-6 sm:w-6" />
                      </motion.div>
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}
