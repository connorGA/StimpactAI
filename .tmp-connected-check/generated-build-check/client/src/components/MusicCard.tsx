import { Play, Pause, Heart, ListPlus } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { savedTrackService } from "@/lib/savedTrackService";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { queryClient } from "@/lib/queryClient";
import AddToPlaylistDialog from "./AddToPlaylistDialog";
import { usePlanLimits } from "@/hooks/usePlanLimits";

interface MusicCardProps {
  id: string;
  title: string;
  artist: string;
  thumbnail: string;
  audioUrl: string;
  duration: string;
  coverPosition?: string;
  genre?: string;
  onPlayStateChange?: () => void;
  isCurrentlyPlaying?: boolean;
  isSaved?: boolean;
  streams?: number;
}

export default function MusicCard({
  id,
  title,
  artist,
  thumbnail,
  duration,
  coverPosition = "center center",
  genre,
  onPlayStateChange,
  isCurrentlyPlaying = false,
  isSaved: initialSaved = false,
  streams = 0,
}: MusicCardProps) {
  const { user } = useAuth();
  const { toast } = useToast();
  const { canSaveTrack, limits, getUpgradeMessage } = usePlanLimits();
  const [playlistDialogOpen, setPlaylistDialogOpen] = useState(false);

  // Fetch saved tracks to check if this track is saved (via secure server proxy)
  const { data: savedTracks } = useQuery({
    queryKey: ['/saved_tracks', user?.id],
    queryFn: () => savedTrackService.getCurrent(),
    enabled: !!user,
  });

  const userSavedTracks = savedTracks || [];
  const userSavedTrack = savedTracks?.find(st => st.track_id === id);
  const isSaved = initialSaved || !!userSavedTrack;

  // Save track mutation
  const saveTrackMutation = useMutation({
    mutationFn: () =>
      savedTrackService.create({
        user_id: user!.id,
        track_id: id,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/saved_tracks', user?.id] });
      toast({
        title: "Track saved",
        description: `"${title}" has been added to your library`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to save track",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Unsave track mutation
  const unsaveTrackMutation = useMutation({
    mutationFn: () => {
      if (!userSavedTrack) throw new Error("Saved track not found");
      return savedTrackService.delete(userSavedTrack.id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/saved_tracks', user?.id] });
      toast({
        title: "Track removed",
        description: `"${title}" has been removed from your library`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to remove track",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handlePlayClick = () => {
    onPlayStateChange?.();
  };

  const handleSaveToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!user) {
      toast({
        title: "Login required",
        description: "Please log in to save tracks",
        variant: "destructive",
      });
      return;
    }

    if (isSaved) {
      unsaveTrackMutation.mutate();
    } else {
      // Check if user can save more tracks based on their plan
      if (!canSaveTrack(userSavedTracks.length)) {
        const upgradeMsg = getUpgradeMessage('savedTracks');
        const title = limits.maxSavedTracks === 0 
          ? "Premium feature" 
          : `Limit reached (${limits.maxSavedTracks} tracks)`;
        toast({
          title,
          description: upgradeMsg || "You've reached your saved tracks limit",
          variant: "destructive",
        });
        return;
      }
      saveTrackMutation.mutate();
    }
  };

  const handleAddToPlaylist = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!user) {
      toast({
        title: "Login required",
        description: "Please log in to add tracks to playlists",
        variant: "destructive",
      });
      return;
    }
    setPlaylistDialogOpen(true);
  };

  return (
    <>
      <Card className="group relative overflow-hidden transition-all duration-200 hover:scale-105">
        <div className="relative aspect-square sm:aspect-square">
          <img
            src={thumbnail}
            alt={title}
            className="h-full w-full object-cover"
            style={{ objectPosition: coverPosition }}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 transition-opacity duration-200 group-hover:opacity-100" />
          <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-200 group-hover:opacity-100">
            <Button
              size="icon"
              className="h-10 w-10 sm:h-14 sm:w-14 rounded-full bg-primary text-primary-foreground shadow-lg hover-elevate active-elevate-2"
              onClick={handlePlayClick}
              data-testid={`button-play-${id}`}
            >
              {isCurrentlyPlaying ? (
                <Pause className="h-3.5 w-3.5 sm:h-6 sm:w-6" />
              ) : (
                <Play className="h-3.5 w-3.5 sm:h-6 sm:w-6" />
              )}
            </Button>
          </div>

          {/* Action buttons - top right */}
          <div className="absolute top-1 right-1 sm:top-2 sm:right-2 flex gap-0.5 sm:gap-2 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
            <Button
              size="icon"
              variant={isSaved ? "default" : "secondary"}
              className={`h-9 w-9 rounded-full backdrop-blur-sm ${isSaved ? '' : 'bg-black/60'}`}
              onClick={handleSaveToggle}
              data-testid={`button-save-${id}`}
            >
              <Heart className={`h-3.5 w-3.5 sm:h-4 sm:w-4 ${isSaved ? 'fill-current' : ''}`} />
            </Button>
            <Button
              size="icon"
              variant="secondary"
              className="h-9 w-9 rounded-full bg-black/60 backdrop-blur-sm"
              onClick={handleAddToPlaylist}
              data-testid={`button-add-to-playlist-${id}`}
            >
              <ListPlus className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            </Button>
          </div>

          <div className="absolute bottom-1 right-1 sm:bottom-2 sm:right-2">
            <div className="rounded-md bg-black/60 px-1 py-0.5 sm:px-2 sm:py-1 text-[10px] sm:text-xs text-white backdrop-blur-sm">
              {duration}
            </div>
          </div>
        </div>
        <div className="p-1 sm:p-4 relative">
          <h3 className="truncate text-xs sm:text-base font-medium text-foreground leading-tight" data-testid={`text-title-${id}`}>
            {title}
          </h3>
          <p className="truncate text-xs sm:text-sm text-muted-foreground leading-tight" data-testid={`text-artist-${id}`}>
            {artist}
          </p>
          {genre && (
            <p className="hidden sm:block truncate text-xs sm:text-sm text-muted-foreground" data-testid={`text-genre-${id}`}>
              Genre: {genre.includes(':') ? genre.split(':')[1].charAt(0).toUpperCase() + genre.split(':')[1].slice(1) : genre}
            </p>
          )}
          {streams > 0 && (
            <div className="absolute bottom-1 right-1 sm:bottom-4 sm:right-4 flex items-center gap-1" data-testid={`text-streams-${id}`}>
              <span className="text-[11px] sm:text-xs text-muted-foreground">{streams.toLocaleString()}</span>
              <Play className="h-2.5 w-2.5 sm:h-3 sm:w-3 text-muted-foreground fill-current" />
            </div>
          )}
        </div>
      </Card>

      <AddToPlaylistDialog
        open={playlistDialogOpen}
        onOpenChange={setPlaylistDialogOpen}
        trackId={id}
        trackTitle={title}
      />
    </>
  );
}