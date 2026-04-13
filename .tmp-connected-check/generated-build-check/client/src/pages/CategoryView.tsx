import { useRoute, Link } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { trackService } from "@/lib/trackService";
import { useSignedTracks, transformSignedTrackForPlayer } from "@/hooks/useSignedTrack";
import { useMusicPlayer } from "@/contexts/MusicPlayerContext";
import MusicCard from "@/components/MusicCard";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Clock, Star, TrendingUp, Music, Loader2 } from "lucide-react";

type CategoryType = "new-releases" | "most-popular" | "trending" | "all";

interface CategoryConfig {
  title: string;
  description: string;
  icon: React.ReactNode;
}

const categoryConfigs: Record<CategoryType, CategoryConfig> = {
  "new-releases": {
    title: "New Releases",
    description: "The 20 newest tracks on the platform",
    icon: <Clock className="h-6 w-6 text-primary" />,
  },
  "most-popular": {
    title: "Most Popular",
    description: "The 20 most streamed tracks of all time",
    icon: <Star className="h-6 w-6 text-primary" />,
  },
  trending: {
    title: "Trending Now",
    description: "The 20 hottest tracks streamed in the last 24 hours",
    icon: <TrendingUp className="h-6 w-6 text-primary" />,
  },
  all: {
    title: "All Tracks",
    description: "Browse all available tracks in alphabetical order",
    icon: <Music className="h-6 w-6 text-primary" />,
  },
};

export default function CategoryView() {
  const [match, params] = useRoute("/explore/:category");
  const category = params?.category as CategoryType;
  const { playSong, currentSong, isPlaying } = useMusicPlayer();

  const { data: tracks, isLoading, error } = useQuery({
    queryKey: ['/tracks'],
    queryFn: () => trackService.getAll(),
  });

  // Get signed URLs for all tracks
  const activeTracks = tracks?.filter(track => !track.is_deleted) || [];
  const signedTracks = useSignedTracks(activeTracks);

  if (!match || !categoryConfigs[category]) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
          <p className="text-muted-foreground">Category not found</p>
        </div>
      </div>
    );
  }

  const config = categoryConfigs[category];

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
          <Link href="/">
            <Button variant="ghost" size="sm" className="gap-2 mb-4" data-testid="button-back-to-explore">
              <ArrowLeft className="h-4 w-4" />
              Back to Explore
            </Button>
          </Link>
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">Loading tracks...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
          <Link href="/">
            <Button variant="ghost" size="sm" className="gap-2 mb-4" data-testid="button-back-to-explore">
              <ArrowLeft className="h-4 w-4" />
              Back to Explore
            </Button>
          </Link>
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <p className="text-destructive mb-2">Failed to load tracks</p>
            <p className="text-muted-foreground text-sm">{error.message}</p>
          </div>
        </div>
      </div>
    );
  }

  // Filter and sort tracks based on category
  let displayTracks = [...signedTracks];

  switch (category) {
    case "new-releases":
      displayTracks = displayTracks
        .sort((a, b) => b.created_at - a.created_at)
        .slice(0, 20);
      break;
    case "most-popular":
      displayTracks = displayTracks
        .sort((a, b) => (b.streams || 0) - (a.streams || 0))
        .slice(0, 20);
      break;
    case "trending":
      const oneDayAgo = Date.now() - (24 * 60 * 60 * 1000);
      displayTracks = displayTracks
        .filter(track => track.last_streamed_at && track.last_streamed_at > oneDayAgo)
        .sort((a, b) => (b.streams || 0) - (a.streams || 0))
        .slice(0, 20);
      break;
    case "all":
      displayTracks = displayTracks
        .sort((a, b) => a.title.localeCompare(b.title));
      break;
  }

  const transformedTracks = displayTracks.map(transformSignedTrackForPlayer);

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
        <Link href="/">
          <Button variant="ghost" size="sm" className="gap-2 mb-4 sm:mb-6" data-testid="button-back-to-explore">
            <ArrowLeft className="h-4 w-4" />
            Back to Explore
          </Button>
        </Link>

        <div className="mb-6 sm:mb-8">
          <div className="flex items-center gap-2 mb-2">
            {config.icon}
            <h1 className="text-2xl sm:text-4xl font-bold text-foreground">{config.title}</h1>
          </div>
          <p className="text-sm sm:text-base text-muted-foreground">{config.description}</p>
        </div>

        {transformedTracks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20">
            <p className="text-muted-foreground mb-2">No tracks available</p>
            <p className="text-sm text-muted-foreground">
              {category === "trending" 
                ? "No tracks have been streamed in the last 24 hours" 
                : "Check back soon for new AI-generated music!"}
            </p>
          </div>
        ) : (
          <>
            <div className="mb-4 text-sm text-muted-foreground">
              Showing {transformedTracks.length} {transformedTracks.length === 1 ? 'track' : 'tracks'}
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2 sm:gap-6">
              {transformedTracks.map((song) => (
                <MusicCard
                  key={song.id}
                  {...song}
                  onPlayStateChange={() => playSong(song)}
                  isCurrentlyPlaying={currentSong?.id === song.id && isPlaying}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
