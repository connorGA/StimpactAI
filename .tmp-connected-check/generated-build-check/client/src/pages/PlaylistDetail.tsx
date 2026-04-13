import { useRoute, useLocation } from "wouter";
import { useQuery, useMutation } from "@tanstack/react-query";
import { playlistService } from "@/lib/playlistService";
import { playlistTrackService } from "@/lib/playlistTrackService";
import { trackService } from "@/lib/trackService";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Play, Pause, Trash2, Loader2, Music, Upload, ImageIcon, Plus, Shuffle } from "lucide-react";
import MusicCard from "@/components/MusicCard";
import { useMusicPlayer } from "@/contexts/MusicPlayerContext";
import { useToast } from "@/hooks/use-toast";
import { queryClient } from "@/lib/queryClient";
import { useSignedTracks, transformSignedTrackForPlayer } from "@/hooks/useSignedTrack";
import PlaylistCoverImage from "@/components/PlaylistCoverImage";
import { getAuthToken } from "@/lib/xanoClient";
import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";

export default function PlaylistDetail() {
  const [, params] = useRoute("/playlists/:id");
  const [, navigate] = useLocation();
  const { playSong, playQueue, currentSong, isPlaying } = useMusicPlayer();
  const { toast } = useToast();
  const { user } = useAuth();
  const playlistId = params?.id;
  const [uploadingCover, setUploadingCover] = useState(false);
  const [shuffleEnabled, setShuffleEnabled] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch playlist details with server-side ownership verification
  const { data: playlist, isLoading: playlistLoading } = useQuery({
    queryKey: ['/playlists', playlistId],
    queryFn: () => playlistService.getOneSecure(playlistId!),
    enabled: !!playlistId,
  });

  // Fetch playlist tracks with server-side ownership verification
  const { data: playlistTracks, isLoading: tracksLoading } = useQuery({
    queryKey: ['/playlist_tracks', playlistId],
    queryFn: () => playlistTrackService.getByPlaylistIdSecure(playlistId!),
    enabled: !!playlistId,
  });

  // Fetch all tracks
  const { data: allTracks } = useQuery({
    queryKey: ['/tracks'],
    queryFn: () => trackService.getAll(),
  });

  // Join with actual track data
  const tracks = (playlistTracks || [])
    .map(pt => {
      const track = allTracks?.find(t => t.id === pt.track_id);
      return track ? { ...track, playlistTrackId: pt.id } : null;
    })
    .filter(Boolean);

  // Get signed URLs for tracks
  const signedTracks = useSignedTracks(tracks as any);

  // Remove track from playlist mutation with ownership verification
  const removeTrackMutation = useMutation({
    mutationFn: (playlistTrackId: string) =>
      playlistTrackService.deleteSecure(playlistId!, playlistTrackId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/playlist_tracks', playlistId] });
      toast({
        title: "Track removed",
        description: "Track has been removed from this playlist",
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

  // Upload cover image
  const uploadCover = async (file: File) => {
    setUploadingCover(true);
    try {
      const token = getAuthToken();
      if (!token) {
        throw new Error('Authentication required');
      }

      const formData = new FormData();
      formData.append('cover', file);

      const response = await fetch('/api/upload/playlist-cover', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to upload cover image');
      }

      const data = await response.json();
      
      await playlistService.updateSecure(playlistId!, { cover_image_url: data.url });
      
      // Invalidate both detail and list queries to update all views
      queryClient.invalidateQueries({ queryKey: ['/playlists', playlistId] });
      queryClient.invalidateQueries({ queryKey: ['/playlists'] });
      
      // Reset file input so same file can be uploaded again
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      
      toast({
        title: "Cover uploaded",
        description: "Playlist cover has been updated successfully",
      });
    } catch (error) {
      toast({
        title: "Upload failed",
        description: error instanceof Error ? error.message : "Failed to upload cover",
        variant: "destructive",
      });
    } finally {
      setUploadingCover(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.type.startsWith('image/')) {
        toast({
          title: "Invalid file type",
          description: "Please select an image file",
          variant: "destructive",
        });
        return;
      }
      uploadCover(file);
    }
  };

  const handlePlayPlaylist = () => {
    if (signedTracks.length === 0) {
      toast({
        title: "No tracks",
        description: "This playlist has no tracks to play",
        variant: "destructive",
      });
      return;
    }

    let tracksToPlay = [...signedTracks];
    
    if (shuffleEnabled) {
      // Fisher-Yates shuffle algorithm
      for (let i = tracksToPlay.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [tracksToPlay[i], tracksToPlay[j]] = [tracksToPlay[j], tracksToPlay[i]];
      }
    }

    const songsQueue = tracksToPlay.map(track => transformSignedTrackForPlayer(track));
    playQueue(songsQueue);
  };

  const isLoading = playlistLoading || tracksLoading;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-3 sm:px-6 py-4 sm:py-8">
          <Button
            variant="ghost"
            className="mb-4 sm:mb-6 gap-2"
            onClick={() => navigate("/playlists")}
            data-testid="button-back-to-playlists"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">Back to Playlists</span>
            <span className="sm:hidden">Back</span>
          </Button>
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">Loading playlist...</p>
          </div>
        </div>
      </div>
    );
  }

  if (!playlist) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-3 sm:px-6 py-4 sm:py-8">
          <Button
            variant="ghost"
            className="mb-4 sm:mb-6 gap-2"
            onClick={() => navigate("/playlists")}
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">Back to Playlists</span>
            <span className="sm:hidden">Back</span>
          </Button>
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <Music className="h-16 w-16 text-muted-foreground mb-4" />
            <h2 className="text-xl font-semibold text-foreground mb-2">Playlist not found</h2>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-3 sm:px-6 py-4 sm:py-8">
        <Button
          variant="ghost"
          className="mb-4 sm:mb-6 gap-2"
          onClick={() => navigate("/playlists")}
          data-testid="button-back-to-playlists"
        >
          <ArrowLeft className="h-4 w-4" />
          <span className="hidden sm:inline">Back to Playlists</span>
          <span className="sm:hidden">Back</span>
        </Button>

        {/* Playlist header */}
        <div className="mb-6 sm:mb-8 flex flex-col gap-4 sm:gap-6 lg:flex-row lg:items-end">
          <div className="relative h-40 w-40 sm:h-48 sm:w-48 mx-auto lg:mx-0">
            <PlaylistCoverImage
              coverImageUrl={playlist.cover_image_url}
              tracks={tracks as any}
              playlistName={playlist.name}
              className="h-40 w-40 sm:h-48 sm:w-48 rounded-lg object-cover shadow-lg"
            />
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="hidden"
              data-testid="input-playlist-cover"
            />
            <Button
              size="icon"
              variant="secondary"
              className="absolute -top-4 -left-4 h-10 w-10 rounded-full shadow-md z-10"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadingCover}
              data-testid="button-upload-cover"
            >
              {uploadingCover ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <Plus className="h-5 w-5" />
              )}
            </Button>
          </div>
          <div className="flex-1 text-center lg:text-left">
            <p className="text-sm text-muted-foreground mb-2">Playlist</p>
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 mb-3 sm:mb-4">
              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-foreground" data-testid="text-playlist-name">
                {playlist.name}
              </h1>
              <div className="flex items-center gap-2 justify-center lg:justify-start">
                <Button
                  size="icon"
                  variant="default"
                  className="h-12 w-12 rounded-full"
                  onClick={handlePlayPlaylist}
                  disabled={signedTracks.length === 0}
                  data-testid="button-play-playlist"
                >
                  <Play className="h-5 w-5 fill-current" />
                </Button>
                <Button
                  size="icon"
                  variant={shuffleEnabled ? "default" : "outline"}
                  className="h-10 w-10 rounded-full"
                  onClick={() => setShuffleEnabled(!shuffleEnabled)}
                  data-testid="button-shuffle-toggle"
                >
                  <Shuffle className={`h-4 w-4 ${shuffleEnabled ? '' : 'text-muted-foreground'}`} />
                </Button>
              </div>
            </div>
            {playlist.description && (
              <p className="text-sm sm:text-base text-muted-foreground mb-3 sm:mb-4">{playlist.description}</p>
            )}
            <p className="text-sm text-muted-foreground">
              {tracks.length} {tracks.length === 1 ? 'track' : 'tracks'}
            </p>
          </div>
        </div>

        {signedTracks.length > 0 ? (
          <div className="space-y-4">
            {signedTracks.map((track: any) => {
              const song = transformSignedTrackForPlayer(track);

              return (
                <div key={track.id} className="flex items-center gap-4 group">
                  <div className="flex-1">
                    <div className="flex items-center gap-4">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-10 w-10"
                        onClick={() => playSong(song)}
                        data-testid={`button-play-track-${track.id}`}
                      >
                        {currentSong?.id === track.id && isPlaying ? (
                          <Pause className="h-5 w-5" />
                        ) : (
                          <Play className="h-5 w-5" />
                        )}
                      </Button>
                      <img
                        src={song.thumbnail}
                        alt={track.title}
                        className="h-14 w-14 rounded object-cover"
                        style={{ objectPosition: song.coverPosition || "center center" }}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-foreground truncate text-sm sm:text-base">{track.title}</p>
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">{track.artist}</p>
                      </div>
                      <p className="text-xs sm:text-sm text-muted-foreground hidden sm:block">{song.duration}</p>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={() => removeTrackMutation.mutate(track.playlistTrackId)}
                        disabled={removeTrackMutation.isPending}
                        data-testid={`button-remove-track-${track.id}`}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 mb-4">
              <Music className="h-10 w-10 text-primary" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">No tracks yet</h2>
            <p className="text-muted-foreground">Add tracks to this playlist to get started</p>
          </div>
        )}
      </div>
    </div>
  );
}
