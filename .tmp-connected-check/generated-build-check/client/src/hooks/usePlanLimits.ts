import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { accountStatusService } from '@/lib/accountStatusService';
import { PLAN_LIMITS, type PlanTier } from '@shared/schema';

export interface PlanLimits {
  maxSavedTracks: number;
  maxPlaylists: number;
  monthlyCredits: number;
  canRequestSongs: boolean;
  canUpvote: boolean;
}

export function usePlanLimits() {
  const { user, isAuthenticated } = useAuth();

  const { data: accountStatus, isLoading } = useQuery({
    queryKey: ['/api/account-status/me'],
    queryFn: () => accountStatusService.getCurrent(),
    enabled: !!user && isAuthenticated,
  });

  const planTier: PlanTier = accountStatus?.plan_tier || 'free';
  // Defensive fallback to ensure we always have valid limits
  const limits: PlanLimits = PLAN_LIMITS[planTier] || PLAN_LIMITS['free'];

  const canSaveTrack = (currentSavedCount: number): boolean => {
    if (!limits) return false;
    return currentSavedCount < limits.maxSavedTracks;
  };

  const canCreatePlaylist = (currentPlaylistCount: number): boolean => {
    if (!limits) return false;
    return currentPlaylistCount < limits.maxPlaylists;
  };

  const getUpgradeMessage = (feature: 'savedTracks' | 'playlists' | 'credits' | 'requests' | 'upvotes'): string => {
    switch (feature) {
      case 'savedTracks':
        if (planTier === 'free') {
          return 'Upgrade to Plus for unlimited saved tracks';
        }
        return '';
      case 'playlists':
        if (planTier === 'free') {
          return 'Upgrade to Plus to create custom playlists';
        }
        if (planTier === 'plus') {
          return 'Upgrade to Premium for unlimited playlists';
        }
        return '';
      case 'credits':
      case 'requests':
      case 'upvotes':
        if (planTier === 'free') {
          return 'Upgrade to Plus to participate in song requests and voting';
        }
        return '';
      default:
        return 'Upgrade for more features';
    }
  };

  return {
    accountStatus,
    planTier,
    limits,
    isLoading,
    canSaveTrack,
    canCreatePlaylist,
    getUpgradeMessage,
  };
}
