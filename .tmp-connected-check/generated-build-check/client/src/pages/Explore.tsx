import MusicCard from "@/components/MusicCard";
import { useMusicPlayer } from "@/contexts/MusicPlayerContext";
import { TrendingUp, Star, Clock, ChevronRight, Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Link } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { trackService } from "@/lib/trackService";
import { useState } from "react";
import { useSignedTracks, transformSignedTrackForPlayer } from "@/hooks/useSignedTrack";

interface Song {
  id: string;
  title: string;
  artist: string;
  thumbnail: string;
  audioUrl: string;
  duration: string;
}

interface SectionProps {
  title: string;
  icon: React.ReactNode;
  songs: Song[];
}

interface MusicSectionProps extends SectionProps {
  categoryPath?: string;
}

function MusicSection({ title, icon, songs, categoryPath }: MusicSectionProps) {
  const { playSong, currentSong, isPlaying } = useMusicPlayer();

  if (songs.length === 0) {
    return null;
  }

  return (
    <div className="mb-6 sm:mb-12">
      <div className="flex items-center justify-between mb-3 sm:mb-6">
        <div className="flex items-center gap-1.5 sm:gap-2">
          {icon}
          <h2 className="text-base sm:text-2xl font-bold text-foreground">{title}</h2>
        </div>
        {categoryPath && (
          <Link href={categoryPath}>
            <Button variant="ghost" size="sm" className="gap-1" data-testid={`button-view-all-${title.toLowerCase().replace(/\s+/g, '-')}`} aria-label={`View all ${title}`}>
              <span className="hidden sm:inline">View All</span>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </Link>
        )}
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2 sm:gap-6">
        {songs.map((song) => (
          <MusicCard
            key={song.id}
            {...song}
            onPlayStateChange={() => playSong(song, 'explore')}
            isCurrentlyPlaying={currentSong?.id === song.id && isPlaying}
          />
        ))}
      </div>
    </div>
  );
}

export default function Explore() {
  const [searchQuery, setSearchQuery] = useState("");
  
  const { data: tracks, isLoading, error } = useQuery({
    queryKey: ['/tracks'],
    queryFn: () => trackService.getAll(),
  });

  // Get signed URLs for all tracks
  const activeTracks = tracks?.filter(track => !track.is_deleted) || [];
  const signedTracks = useSignedTracks(activeTracks);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
          <div className="flex items-center justify-between mb-3 sm:mb-8">
            <div>
              <h1 className="text-xl sm:text-4xl font-bold text-foreground mb-0.5 sm:mb-2">Explore</h1>
              <p className="text-xs sm:text-base text-muted-foreground">Discover new AI-generated music</p>
            </div>
          </div>
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">Loading music...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
          <div className="flex items-center justify-between mb-3 sm:mb-8">
            <div>
              <h1 className="text-xl sm:text-4xl font-bold text-foreground mb-0.5 sm:mb-2">Explore</h1>
              <p className="text-xs sm:text-base text-muted-foreground">Discover new AI-generated music</p>
            </div>
          </div>
          <div className="flex flex-col items-center justify-center py-12 sm:py-20">
            <p className="text-destructive mb-2">Failed to load tracks</p>
            <p className="text-muted-foreground text-sm">{error.message}</p>
          </div>
        </div>
      </div>
    );
  }

  // Filter tracks based on search query
  const filteredTracks = signedTracks.filter(track => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    return (
      track.title.toLowerCase().includes(query) ||
      (track.artist && track.artist.toLowerCase().includes(query))
    );
  });

  const transformedTracks = filteredTracks.map(transformSignedTrackForPlayer);

  // Categorize tracks
  const sortedByDate = [...filteredTracks].sort((a, b) => b.created_at - a.created_at);
  const newReleases = sortedByDate.slice(0, 4).map(transformSignedTrackForPlayer);
  
  // Most Popular: Sort by total streams (highest first)
  const sortedByStreams = [...filteredTracks].sort((a, b) => (b.streams || 0) - (a.streams || 0));
  const mostPopular = sortedByStreams.slice(0, 4).map(transformSignedTrackForPlayer);
  
  // Trending Now: Tracks streamed in last 24 hours, sorted by streams
  const oneDayAgo = Date.now() - (24 * 60 * 60 * 1000);
  const recentlyStreamed = filteredTracks.filter(track => 
    track.last_streamed_at && track.last_streamed_at > oneDayAgo
  );
  const sortedTrending = [...recentlyStreamed].sort((a, b) => (b.streams || 0) - (a.streams || 0));
  const trending = sortedTrending.slice(0, 4).map(transformSignedTrackForPlayer);

  const hasAnyTracks = newReleases.length > 0 || mostPopular.length > 0 || trending.length > 0;

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-2 sm:px-6 py-3 sm:py-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-0 mb-3 sm:mb-6">
          <div>
            <h1 className="text-xl sm:text-4xl font-bold text-foreground mb-0.5 sm:mb-2">Explore</h1>
            <p className="text-xs sm:text-base text-muted-foreground">Discover new AI-generated music</p>
          </div>
          <div className="flex items-center gap-2 sm:gap-4">
            <Link href="/explore/all">
              <Button variant="ghost" size="sm" data-testid="button-view-all-tracks">
                View All Tracks
              </Button>
            </Link>
            <Link href="/leaderboard" className="text-primary hover:underline text-xs sm:text-sm font-medium" data-testid="link-request-song">
              Request a song →
            </Link>
          </div>
        </div>

        <div className="relative mb-4 sm:mb-8">
          <Search className="absolute left-2 sm:left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 sm:h-4 sm:w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search by title or artist..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 sm:pl-10 text-sm sm:text-base h-9 sm:h-10"
            data-testid="input-search"
          />
        </div>

        {!hasAnyTracks ? (
          <div className="flex flex-col items-center justify-center py-20">
            <p className="text-muted-foreground mb-2">
              {searchQuery ? `No tracks found for "${searchQuery}"` : "No tracks available yet"}
            </p>
            <p className="text-sm text-muted-foreground">
              {searchQuery ? "Try a different search term" : "Check back soon for new AI-generated music!"}
            </p>
          </div>
        ) : (
          <>
            <MusicSection
              title="New Releases"
              icon={<Clock className="h-4 w-4 sm:h-6 sm:w-6 text-primary" />}
              songs={newReleases}
              categoryPath="/explore/new-releases"
            />

            <MusicSection
              title="Most Popular"
              icon={<Star className="h-4 w-4 sm:h-6 sm:w-6 text-primary" />}
              songs={mostPopular}
              categoryPath="/explore/most-popular"
            />

            <MusicSection
              title="Trending Now"
              icon={<TrendingUp className="h-4 w-4 sm:h-6 sm:w-6 text-primary" />}
              songs={trending}
              categoryPath="/explore/trending"
            />
          </>
        )}
      </div>
    </div>
  );
}
