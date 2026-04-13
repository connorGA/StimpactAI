import { useMusicPlayer } from "@/contexts/MusicPlayerContext";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Play, Pause, SkipBack, SkipForward, Volume2 } from "lucide-react";
import { useState, useEffect } from "react";

function formatTime(seconds: number): string {
  if (isNaN(seconds)) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export default function MusicPlayerBar() {
  const { currentSong, isPlaying, currentTime, duration, togglePlay, seekTo, audioRef, playNext, playPrevious, canPlayNext, canPlayPrevious } = useMusicPlayer();
  const [volume, setVolume] = useState(() => {
    const savedVolume = localStorage.getItem("music-player-volume");
    return savedVolume ? parseInt(savedVolume) : 75;
  });

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = volume / 100;
    }
  }, [audioRef, volume]);

  if (!currentSong) {
    return null;
  }

  const handleSeek = (value: number[]) => {
    seekTo(value[0]);
  };

  const handleVolumeChange = (value: number[]) => {
    const newVolume = value[0];
    setVolume(newVolume);
    localStorage.setItem("music-player-volume", newVolume.toString());
    if (audioRef.current) {
      audioRef.current.volume = newVolume / 100;
    }
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-background/95 backdrop-blur-xl">
      <div className="container mx-auto px-2 sm:px-6 py-2 sm:py-3">
        {/* Main Player Row */}
        <div className="flex flex-col sm:flex-row items-center gap-2 sm:gap-4">
          {/* Mobile: Song Info and Compact Controls */}
          <div className="flex items-start gap-2 w-full sm:hidden">
            <img
              src={currentSong.thumbnail}
              alt={currentSong.title}
              className="h-12 w-12 rounded-md object-cover flex-shrink-0"
              style={{ objectPosition: currentSong.coverPosition || "center center" }}
              data-testid="img-player-thumbnail"
            />
            <div className="min-w-0 flex-1 flex flex-col gap-1">
              <div>
                <h4 className="font-medium text-foreground truncate text-sm" data-testid="text-player-title">
                  {currentSong.title}
                </h4>
                <p className="text-xs text-muted-foreground truncate" data-testid="text-player-artist">
                  {currentSong.artist}
                </p>
              </div>
              {/* Timeline and Controls in the middle space */}
              <div className="flex items-center gap-1.5">
                <Button 
                  size="icon" 
                  variant="ghost"
                  disabled={!canPlayPrevious}
                  onClick={playPrevious}
                  className="h-7 w-7 flex-shrink-0"
                  data-testid="button-previous-mobile"
                >
                  <SkipBack className="h-3.5 w-3.5" />
                </Button>
                <div className="flex items-center gap-1 flex-1">
                  <span className="text-[10px] text-muted-foreground w-7 text-right" data-testid="text-current-time-mobile">
                    {formatTime(currentTime)}
                  </span>
                  <Slider
                    value={[currentTime]}
                    max={duration || 100}
                    step={1}
                    onValueChange={handleSeek}
                    className="flex-1"
                    data-testid="slider-progress-mobile"
                  />
                  <span className="text-[10px] text-muted-foreground w-7" data-testid="text-duration-mobile">
                    {formatTime(duration)}
                  </span>
                </div>
                <Button 
                  size="icon" 
                  variant="ghost"
                  disabled={!canPlayNext}
                  onClick={playNext}
                  className="h-7 w-7 flex-shrink-0"
                  data-testid="button-next-mobile"
                >
                  <SkipForward className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
            <Button
              size="icon"
              className="h-10 w-10 flex-shrink-0"
              onClick={togglePlay}
              data-testid="button-play-pause"
            >
              {isPlaying ? (
                <Pause className="h-5 w-5" />
              ) : (
                <Play className="h-5 w-5" />
              )}
            </Button>
          </div>

          {/* Desktop: Song Info */}
          <div className="hidden sm:flex items-center gap-3 flex-1 min-w-0">
            <img
              src={currentSong.thumbnail}
              alt={currentSong.title}
              className="h-14 w-14 rounded-md object-cover flex-shrink-0"
              style={{ objectPosition: currentSong.coverPosition || "center center" }}
              data-testid="img-player-thumbnail"
            />
            <div className="min-w-0 flex-1">
              <h4 className="font-medium text-foreground truncate text-base" data-testid="text-player-title">
                {currentSong.title}
              </h4>
              <p className="text-sm text-muted-foreground truncate" data-testid="text-player-artist">
                {currentSong.artist}
              </p>
            </div>
          </div>

          {/* Desktop: Controls */}
          <div className="hidden sm:flex flex-col items-center gap-2 flex-1 max-w-2xl">
            <div className="flex items-center gap-2">
              <Button 
                size="icon" 
                variant="ghost"
                disabled={!canPlayPrevious}
                onClick={playPrevious}
                data-testid="button-previous"
              >
                <SkipBack className="h-5 w-5" />
              </Button>
              <Button
                size="icon"
                className="h-10 w-10"
                onClick={togglePlay}
                data-testid="button-play-pause"
              >
                {isPlaying ? (
                  <Pause className="h-5 w-5" />
                ) : (
                  <Play className="h-5 w-5" />
                )}
              </Button>
              <Button 
                size="icon" 
                variant="ghost"
                disabled={!canPlayNext}
                onClick={playNext}
                data-testid="button-next"
              >
                <SkipForward className="h-5 w-5" />
              </Button>
            </div>
            
            <div className="flex items-center gap-2 w-full">
              <span className="text-xs text-muted-foreground w-10 text-right" data-testid="text-current-time">
                {formatTime(currentTime)}
              </span>
              <Slider
                value={[currentTime]}
                max={duration || 100}
                step={1}
                onValueChange={handleSeek}
                className="flex-1"
                data-testid="slider-progress"
              />
              <span className="text-xs text-muted-foreground w-10" data-testid="text-duration">
                {formatTime(duration)}
              </span>
            </div>
          </div>

          <div className="hidden lg:flex items-center gap-2 flex-1 justify-end">
            <Volume2 className="h-5 w-5 text-muted-foreground" />
            <Slider
              value={[volume]}
              max={100}
              step={1}
              onValueChange={handleVolumeChange}
              className="w-24"
              data-testid="slider-volume"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
