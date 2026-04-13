import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ListMusic, Plus, Check, Loader2 } from "lucide-react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { playlistService } from "@/lib/playlistService";
import { playlistTrackService } from "@/lib/playlistTrackService";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { queryClient } from "@/lib/queryClient";

interface AddToPlaylistDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trackId: string;
  trackTitle: string;
}

export default function AddToPlaylistDialog({
  open,
  onOpenChange,
  trackId,
  trackTitle,
}: AddToPlaylistDialogProps) {
  const { user } = useAuth();
  const { toast } = useToast();
  const [addedPlaylists, setAddedPlaylists] = useState<Set<string>>(new Set());

  // Reset added playlists when dialog closes
  useEffect(() => {
    if (!open) {
      setAddedPlaylists(new Set());
    }
  }, [open]);

  // Fetch user's playlists (via secure server proxy)
  const { data: allPlaylists, isLoading: playlistsLoading } = useQuery({
    queryKey: ['/playlists', user?.id],
    queryFn: () => playlistService.getCurrent(),
    enabled: !!user && open,
  });

  const userPlaylists = allPlaylists?.filter(p => !p.is_deleted) || [];

  const addToPlaylistMutation = useMutation({
    mutationFn: (playlistId: string) =>
      playlistTrackService.create({
        playlist_id: playlistId,
        track_id: trackId,
        sort_index: 0,
        added_at: Date.now(),
      }),
    onSuccess: (_, playlistId) => {
      setAddedPlaylists(prev => new Set(Array.from(prev).concat(playlistId)));
      queryClient.invalidateQueries({ queryKey: ['/playlist_tracks', playlistId] });
      queryClient.invalidateQueries({ queryKey: ['/playlists', playlistId] });
      
      const playlist = userPlaylists.find(p => p.id === playlistId);
      toast({
        title: "Added to playlist",
        description: `"${trackTitle}" has been added to "${playlist?.name}"`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to add to playlist",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handlePlaylistClick = (playlistId: string) => {
    addToPlaylistMutation.mutate(playlistId);
  };

  const isLoading = playlistsLoading;
  const isMutating = addToPlaylistMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add to Playlist</DialogTitle>
          <DialogDescription>
            Choose a playlist to add "{trackTitle}"
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
            <p className="text-sm text-muted-foreground">Loading playlists...</p>
          </div>
        ) : userPlaylists.length > 0 ? (
          <ScrollArea className="max-h-[400px]">
            <div className="space-y-2">
              {userPlaylists.map((playlist) => {
                const isAdded = addedPlaylists.has(playlist.id);
                
                return (
                  <Button
                    key={playlist.id}
                    variant={isAdded ? "default" : "outline"}
                    className="w-full justify-between"
                    onClick={() => handlePlaylistClick(playlist.id)}
                    disabled={isMutating || isAdded}
                    data-testid={`playlist-option-${playlist.id}`}
                  >
                    <span className="flex items-center gap-2">
                      <ListMusic className="h-4 w-4" />
                      <span className="truncate">{playlist.name}</span>
                    </span>
                    {isAdded ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Plus className="h-4 w-4" />
                    )}
                  </Button>
                );
              })}
            </div>
          </ScrollArea>
        ) : (
          <div className="flex flex-col items-center justify-center py-8">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 mb-4">
              <ListMusic className="h-8 w-8 text-primary" />
            </div>
            <p className="text-sm text-muted-foreground mb-4">No playlists yet</p>
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              Create a playlist first
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
