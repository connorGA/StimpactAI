import MusicCard from "@/components/MusicCard";
import { Music, Loader2, Heart, LogIn } from "lucide-react";
import { useMusicPlayer } from "@/contexts/MusicPlayerContext";
import { useQuery } from "@tanstack/react-query";
import { savedTrackService } from "@/lib/savedTrackService";
import { trackService } from "@/lib/trackService";
import { useAuth } from "@/contexts/AuthContext";
import { useSignedTracks, transformSignedTrackForPlayer } from "@/hooks/useSignedTrack";
import { Button } from "@/components/ui/button";
import { useLocation } from "wouter";

export default function Library() {
  const { playQueue, currentSong, isPlaying } = useMusicPlayer();
  const { user, isAuthenticated } = useAuth();
  const [, navigate] = useLocation();
  
  // Fetch user's saved tracks (scoped to current user via secure server proxy)
  const { data: savedTracks, isLoading: savedLoading } = useQuery({
    queryKey: ['/saved_tracks', user?.id],
    queryFn: () => savedTrackService.getCurrent(),
    enabled: !!user,
  });

  // Fetch all tracks to join with saved tracks
  const { data: allTracks, isLoading: tracksLoading } = useQuery({
    queryKey: ['/tracks'],
    queryFn: () => trackService.getAll(),
  });

  const isLoading = savedLoading || tracksLoading;

  // Join saved tracks with track data
  const savedTrackIds = new Set(savedTracks?.map(st => st.track_id) || []);
  const userTracks = allTracks?.filter(track => 
    savedTrackIds.has(track.id) && !track.is_deleted
  ) || [];

  // Get signed URLs for tracks
  const signedTracks = useSignedTracks(userTracks);

  // Show login prompt if not authenticated
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
          <div className="flex items-center justify-between mb-4 sm:mb-8">
            <div>
              <h1 className="text-lg sm:text-3xl font-bold text-foreground mb-0.5 sm:mb-2 flex items-center gap-1.5 sm:gap-3">
                <Heart className="h-5 w-5 sm:h-8 sm:w-8 text-primary fill-primary" />
                Library
              </h1>
              <p className="text-xs sm:text-base text-muted-foreground">Your personal collection of favorite songs</p>
            </div>
          </div>
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 mb-4">
              <Heart className="h-10 w-10 text-primary" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">Log in to access Library</h2>
            <p className="text-sm sm:text-base text-muted-foreground mb-6 text-center px-4">
              Sign in to save and organize your favorite tracks
            </p>
            <Button className="gap-2" onClick={() => navigate("/login")}>
              <LogIn className="h-4 w-4" />
              Log In
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
          <div className="flex items-center justify-between mb-4 sm:mb-8">
            <div>
              <h1 className="text-lg sm:text-3xl font-bold text-foreground mb-0.5 sm:mb-2 flex items-center gap-1.5 sm:gap-3">
                <Heart className="h-5 w-5 sm:h-8 sm:w-8 text-primary fill-primary" />
                Saved Tracks
              </h1>
              <p className="text-xs sm:text-base text-muted-foreground">Your personal collection of favorite songs</p>
            </div>
          </div>
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">Loading your library...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-3 sm:px-6 py-4 sm:py-8">
        <div className="flex items-center justify-between mb-6 sm:mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-foreground mb-1 sm:mb-2 flex items-center gap-2 sm:gap-3">
              <Heart className="h-6 w-6 sm:h-8 sm:w-8 text-primary fill-primary" />
              Saved Tracks
            </h1>
            <p className="text-sm sm:text-base text-muted-foreground">Your personal collection of favorite songs</p>
          </div>
        </div>

        {signedTracks.length > 0 ? (
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2 sm:gap-6">
            {signedTracks.map((track, index) => {
              const song = transformSignedTrackForPlayer(track);
              return (
                <MusicCard
                  key={track.id}
                  {...song}
                  coverPosition={song.coverPosition}
                  onPlayStateChange={() => {
                    // Build queue starting from clicked song
                    const allSongs = signedTracks.map(t => transformSignedTrackForPlayer(t));
                    const queueFromHere = [...allSongs.slice(index), ...allSongs.slice(0, index)];
                    playQueue(queueFromHere, 'library');
                  }}
                  isCurrentlyPlaying={currentSong?.id === track.id && isPlaying}
                  isSaved={true}
                />
              );
            })}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 mb-4">
              <Heart className="h-10 w-10 text-primary" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">No saved tracks yet</h2>
            <p className="text-sm sm:text-base text-muted-foreground mb-6 text-center px-4">Start exploring and save your favorite songs!</p>
          </div>
        )}
      </div>
    </div>
  );
}
