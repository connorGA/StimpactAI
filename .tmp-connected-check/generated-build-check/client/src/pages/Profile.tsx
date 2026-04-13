import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { User, Mail, Calendar, Music, ListMusic, Heart, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { playlistService } from "@/lib/playlistService";
import { savedTrackService } from "@/lib/savedTrackService";

export default function Profile() {
  const { user } = useAuth();
  
  const { data: playlists, isLoading: isLoadingPlaylists, error: playlistsError } = useQuery({
    queryKey: ['/playlists', user?.id],
    queryFn: () => playlistService.getCurrent(),
    enabled: !!user,
  });

  const { data: savedTracks, isLoading: isLoadingSavedTracks, error: savedTracksError } = useQuery({
    queryKey: ['/saved_tracks', user?.id],
    queryFn: () => savedTrackService.getCurrent(),
    enabled: !!user,
  });

  const userPlaylists = playlists?.filter((p: any) => !p.is_deleted) || [];
  const userSavedTracks = savedTracks || [];
  
  const isLoadingStats = isLoadingPlaylists || isLoadingSavedTracks;
  const hasStatsError = playlistsError || savedTracksError;
  
  const joinDate = user?.created_at 
    ? new Date(user.created_at * 1000).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
    : 'Unknown';

  if (!user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-12 w-12 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-3 sm:px-6 py-4 sm:py-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-foreground mb-6 sm:mb-8">Profile</h1>
        
        <div className="grid gap-4 sm:gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-1 p-4 sm:p-6">
            <div className="flex flex-col items-center text-center">
              <Avatar className="h-24 w-24 sm:h-32 sm:w-32 mb-4">
                <AvatarImage src={user.avatar_url} />
                <AvatarFallback className="text-xl sm:text-2xl">
                  {(user.username || user.email || '??').slice(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              
              <h2 className="text-xl sm:text-2xl font-bold text-foreground mb-1" data-testid="text-username">
                {user.username || user.name}
              </h2>
              
              <div className="flex items-center gap-2 text-muted-foreground mb-3 sm:mb-4">
                <Mail className="h-4 w-4" />
                <span className="text-xs sm:text-sm truncate max-w-full" data-testid="text-email">{user.email}</span>
              </div>
              
              <div className="flex items-center gap-2 text-muted-foreground mb-4 sm:mb-6">
                <Calendar className="h-4 w-4" />
                <span className="text-xs sm:text-sm">Joined {joinDate}</span>
              </div>
            </div>
          </Card>
          
          <Card className="lg:col-span-2 p-4 sm:p-6">
            <h3 className="text-xl font-semibold text-foreground mb-6">Statistics</h3>
            
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col items-center p-6 rounded-lg bg-primary/5 hover-elevate">
                <ListMusic className="h-8 w-8 text-primary mb-3" />
                <div className="text-3xl font-bold text-foreground mb-1" data-testid="text-playlists-count">
                  {isLoadingStats ? (
                    <Loader2 className="h-8 w-8 animate-spin" />
                  ) : hasStatsError ? (
                    '—'
                  ) : (
                    userPlaylists.length
                  )}
                </div>
                <div className="text-sm text-muted-foreground">Playlists</div>
              </div>
              
              <div className="flex flex-col items-center p-6 rounded-lg bg-primary/5 hover-elevate">
                <Heart className="h-8 w-8 text-primary mb-3" />
                <div className="text-3xl font-bold text-foreground mb-1" data-testid="text-favorites-count">
                  {isLoadingStats ? (
                    <Loader2 className="h-8 w-8 animate-spin" />
                  ) : hasStatsError ? (
                    '—'
                  ) : (
                    userSavedTracks.length
                  )}
                </div>
                <div className="text-sm text-muted-foreground">Favorites</div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
