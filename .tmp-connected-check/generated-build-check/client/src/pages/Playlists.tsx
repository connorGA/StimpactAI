import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ListMusic, Plus, Music, Play, Loader2, Crown, AlertCircle, LogIn } from "lucide-react";
import { useLocation } from "wouter";
import { Badge } from "@/components/ui/badge";
import { useQuery, useMutation } from "@tanstack/react-query";
import { playlistService } from "@/lib/playlistService";
import { useAuth } from "@/contexts/AuthContext";
import { usePlanLimits } from "@/hooks/usePlanLimits";
import { useState } from "react";
import PlaylistCoverImage from "@/components/PlaylistCoverImage";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { queryClient } from "@/lib/queryClient";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import PurchaseCreditsDialog from "@/components/PurchaseCreditsDialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export default function Playlists() {
  const { user, isAuthenticated } = useAuth();
  const { toast } = useToast();
  const { canCreatePlaylist, limits, getUpgradeMessage, planTier } = usePlanLimits();
  const [, navigate] = useLocation();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [upgradeDialogOpen, setUpgradeDialogOpen] = useState(false);
  const [playlistName, setPlaylistName] = useState("");
  const [playlistDescription, setPlaylistDescription] = useState("");
  const [upgradeDialogTab, setUpgradeDialogTab] = useState<'subscriptions' | 'credits'>('subscriptions');


  const { data: allPlaylists, isLoading } = useQuery({
    queryKey: ['/playlists', user?.id],
    queryFn: () => playlistService.getCurrent(),
    enabled: !!user,
  });

  const createPlaylistMutation = useMutation({
    mutationFn: (data: { name: string; description?: string }) =>
      playlistService.create({
        user_id: user!.id,
        name: data.name,
        description: data.description,
        privacy: 'private',
        cover_image_url: '',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/playlists', user?.id] });
      setDialogOpen(false);
      setPlaylistName("");
      setPlaylistDescription("");
      toast({
        title: "Playlist created!",
        description: "Your new playlist has been created successfully.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to create playlist",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handleCreatePlaylist = () => {
    if (playlistName.trim()) {
      // Check if user can create more playlists based on their plan
      if (!canCreatePlaylist(playlists.length)) {
        const upgradeMsg = getUpgradeMessage('playlists');
        const limitText = limits.maxPlaylists === Infinity ? 'unlimited' : limits.maxPlaylists;
        toast({
          title: `Limit reached (${limitText} playlists)`,
          description: upgradeMsg || "You've reached your playlist limit",
          variant: "destructive",
        });
        return;
      }

      createPlaylistMutation.mutate({
        name: playlistName,
        description: playlistDescription,
      });
    }
  };

  // Filter to show only non-deleted playlists (already filtered by user from API)
  const playlists = allPlaylists?.filter(p => !p.is_deleted) || [];

  const canCreate = canCreatePlaylist(playlists.length);
  const limitText = limits.maxPlaylists === Infinity ? 'unlimited' : limits.maxPlaylists;

  // Show login prompt if not authenticated
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
          <div className="flex items-center justify-between mb-4 sm:mb-8">
            <div>
              <h1 className="text-lg sm:text-3xl font-bold text-foreground mb-0.5 sm:mb-2">Playlists</h1>
              <p className="text-xs sm:text-base text-muted-foreground">Organize your favorite tracks</p>
            </div>
          </div>
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 mb-4">
              <ListMusic className="h-10 w-10 text-primary" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">Log in to access Playlists</h2>
            <p className="text-sm sm:text-base text-muted-foreground mb-6 text-center px-4">
              Sign in to create and manage your playlists
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
              <h1 className="text-lg sm:text-3xl font-bold text-foreground mb-0.5 sm:mb-2">My Playlists</h1>
              <p className="text-xs sm:text-base text-muted-foreground">Organize your favorite tracks</p>
            </div>
          </div>
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">Loading playlists...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-0 mb-4 sm:mb-8">
          <div>
            <h1 className="text-lg sm:text-3xl font-bold text-foreground mb-0.5 sm:mb-2">My Playlists</h1>
            <p className="text-xs sm:text-base text-muted-foreground">
              {playlists.length} of {limitText} playlists used
            </p>
          </div>
          {planTier === 'free' ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <div>
                  <Button 
                    className="gap-2" 
                    onClick={() => {
                      if (canCreate) {
                        setDialogOpen(true);
                      } else {
                        const upgradeMsg = getUpgradeMessage('playlists');
                        toast({
                          title: `Limit reached (${limitText} playlists)`,
                          description: upgradeMsg || "You've reached your playlist limit",
                          variant: "destructive",
                        });
                      }
                    }}
                    variant={canCreate ? "default" : "secondary"}
                    data-testid="button-create-playlist"
                  >
                    <Plus className="h-4 w-4" />
                    Create Playlist
                  </Button>
                </div>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-xs">
                <p className="text-sm">Upgrade to Plus or Premium to create playlists</p>
              </TooltipContent>
            </Tooltip>
          ) : (
            <Button 
              className="gap-2" 
              onClick={() => {
                if (canCreate) {
                  setDialogOpen(true);
                } else {
                  const upgradeMsg = getUpgradeMessage('playlists');
                  toast({
                    title: `Limit reached (${limitText} playlists)`,
                    description: upgradeMsg || "You've reached your playlist limit",
                    variant: "destructive",
                  });
                }
              }}
              variant={canCreate ? "default" : "secondary"}
              data-testid="button-create-playlist"
            >
              <Plus className="h-4 w-4" />
              Create Playlist
            </Button>
          )}
        </div>

        {planTier === 'free' && (
          <Alert className="mb-8 border-primary/20 bg-primary/5" data-testid="alert-upgrade-playlists">
            <AlertCircle className="h-5 w-5 text-primary" />
            <AlertTitle className="text-foreground font-semibold">Upgrade to Create Playlists</AlertTitle>
            <AlertDescription className="text-muted-foreground">
              You're on the Free plan, which doesn't include playlist creation. 
              Upgrade to Plus ($4.99/month) to create up to 3 playlists, or Premium ($9.99/month) for unlimited playlists.
              <div className="mt-3">
                <Button 
                  size="sm" 
                  className="gap-2"
                  onClick={() => {
                    setUpgradeDialogTab('subscriptions');
                    setUpgradeDialogOpen(true);
                  }}
                  data-testid="button-upgrade-from-banner"
                >
                  <Crown className="h-4 w-4" />
                  View Plans
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        )}

        {playlists.length > 0 ? (
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2 sm:gap-6">
            {playlists.map((playlist) => (
              <Card 
                key={playlist.id} 
                className="group overflow-hidden hover-elevate transition-all duration-200 cursor-pointer"
                onClick={() => navigate(`/playlists/${playlist.id}`)}
                data-testid={`card-playlist-${playlist.id}`}
              >
                <div className="relative aspect-square">
                  <PlaylistCoverImage
                    coverImageUrl={playlist.cover_image_url}
                    tracks={[]}
                    playlistName={playlist.name}
                    className="h-full w-full object-cover"
                  />
                  <Badge className="absolute top-1 right-1 sm:top-2 sm:right-2 gap-0.5 sm:gap-1.5 text-[9px] sm:text-xs bg-black/60 backdrop-blur-sm px-1 sm:px-2" variant="secondary">
                    <Music className="h-2 w-2 sm:h-3 sm:w-3" />
                    {playlist.privacy}
                  </Badge>
                </div>
                <div className="p-1 sm:p-4">
                  <h3 className="text-xs sm:text-base font-medium text-foreground mb-0 sm:mb-1 truncate leading-tight" data-testid={`text-playlist-name-${playlist.id}`}>
                    {playlist.name}
                  </h3>
                  <p className="hidden sm:block text-xs sm:text-sm text-muted-foreground line-clamp-2">
                    {playlist.description || "No description"}
                  </p>
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 mb-4">
              <ListMusic className="h-10 w-10 text-primary" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">No playlists yet</h2>
            <p className="text-sm sm:text-base text-muted-foreground mb-6 text-center px-4">Create your first playlist to get started</p>
            {planTier === 'free' ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <div>
                    <Button className="gap-2" onClick={() => setDialogOpen(true)} data-testid="button-create-first-playlist">
                      <Plus className="h-4 w-4" />
                      Create Playlist
                    </Button>
                  </div>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                  <p className="text-sm">Upgrade to Plus or Premium to create playlists</p>
                </TooltipContent>
              </Tooltip>
            ) : (
              <Button className="gap-2" onClick={() => setDialogOpen(true)} data-testid="button-create-first-playlist">
                <Plus className="h-4 w-4" />
                Create Playlist
              </Button>
            )}
          </div>
        )}

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Playlist</DialogTitle>
              <DialogDescription>
                Give your playlist a name and description to organize your favorite tracks.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="playlist-name">Name</Label>
                <Input
                  id="playlist-name"
                  placeholder="My Awesome Playlist"
                  value={playlistName}
                  onChange={(e) => setPlaylistName(e.target.value)}
                  data-testid="input-playlist-name"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="playlist-description">Description (optional)</Label>
                <Textarea
                  id="playlist-description"
                  placeholder="Add a description..."
                  value={playlistDescription}
                  onChange={(e) => setPlaylistDescription(e.target.value)}
                  data-testid="input-playlist-description"
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setDialogOpen(false)}
                data-testid="button-cancel-playlist"
              >
                Cancel
              </Button>
              <Button
                onClick={handleCreatePlaylist}
                disabled={!playlistName.trim() || createPlaylistMutation.isPending}
                data-testid="button-submit-playlist"
              >
                {createPlaylistMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    <Plus className="h-4 w-4 mr-2" />
                    Create Playlist
                  </>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <PurchaseCreditsDialog
          open={upgradeDialogOpen}
          onOpenChange={setUpgradeDialogOpen}
          defaultTab={upgradeDialogTab}
        />
      </div>
    </div>
  );
}