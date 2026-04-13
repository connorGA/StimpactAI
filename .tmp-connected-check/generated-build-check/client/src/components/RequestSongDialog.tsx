import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Music, Coins, Sparkles } from "lucide-react";
import GenreWheel from "./GenreWheel";
import { GENRES } from "@/lib/genres";

interface RequestSongDialogProps {
  onSubmit?: (songName: string, artistName: string, genre: string) => void;
  trigger?: React.ReactNode;
  userCredits?: number;
  requestCost?: number;
  onUpgradeClick?: () => void;
}

export default function RequestSongDialog({
  onSubmit,
  trigger,
  userCredits = 0,
  requestCost = 200,
  onUpgradeClick,
}: RequestSongDialogProps) {
  const [open, setOpen] = useState(false);
  const [songName, setSongName] = useState("");
  const [artistName, setArtistName] = useState("");
  const [genre, setGenre] = useState("");

  const hasEnoughCredits = userCredits >= requestCost;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (songName.trim() && artistName.trim() && genre && hasEnoughCredits) {
      onSubmit?.(songName, artistName, genre);
      setSongName("");
      setArtistName("");
      setGenre("");
      setOpen(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button size="lg" className="gap-2" data-testid="button-request-song">
            <Music className="h-5 w-5" />
            Request Song
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-[95vw] sm:max-w-5xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg sm:text-2xl">
            <Sparkles className="h-5 w-5 sm:h-6 sm:w-6 text-primary" />
            Request AI-Generated Music
          </DialogTitle>
          <DialogDescription className="text-xs sm:text-sm">
            Choose a genre and tell us what you'd like to hear. Songs with 30 community votes get created!
          </DialogDescription>
        </DialogHeader>

        {/* Credit Cost Banner */}
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-2 sm:p-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Coins className="h-4 w-4 sm:h-5 sm:w-5 text-primary shrink-0" />
              <span className="font-medium text-sm sm:text-base">
                Request Cost: {requestCost} credits
              </span>
            </div>
            <Button
              variant="default"
              size="sm"
              onClick={onUpgradeClick}
              className="gap-2 w-full sm:w-auto"
            >
              <Coins className="h-4 w-4" />
              Add Credits
            </Button>
          </div>
          {!hasEnoughCredits && (
            <p className="text-xs sm:text-sm text-destructive mt-2">
              You need {requestCost - userCredits} more credits to submit a request
            </p>
          )}</div>

        <form onSubmit={handleSubmit}>
          {/* Two-column layout: Genre wheel on left, form on right */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-8 mb-4 sm:mb-6">
            {/* Left column: Genre Selection */}
            <div className="space-y-3 sm:space-y-4">
              <div>
                <h3 className="text-base sm:text-lg font-semibold mb-1 sm:mb-2">Select Genre</h3>
                <p className="text-xs sm:text-sm text-muted-foreground mb-2 sm:mb-4">
                  Click a genre to explore sub-genres
                </p>
              </div>
              <GenreWheel
                value={genre}
                onValueChange={setGenre}
              />
            </div>

            {/* Right column: Song Details */}
            <div className="space-y-3 sm:space-y-6">
              <div>
                <h3 className="text-base sm:text-lg font-semibold mb-2 sm:mb-4">Song Details</h3>
              </div>

              <div className="space-y-2">
                <Label htmlFor="song-name" className="text-sm sm:text-base">Song Name</Label>
                <Input
                  id="song-name"
                  placeholder="e.g., Epic Space Battle Theme"
                  value={songName}
                  onChange={(e) => setSongName(e.target.value)}
                  data-testid="input-song-name"
                  maxLength={100}
                  className="text-sm sm:text-base"
                />
                <p className="text-xs text-muted-foreground">
                  {songName.length}/100 characters
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="artist-name" className="text-sm sm:text-base">Artist Name</Label>
                <Input
                  id="artist-name"
                  placeholder="e.g., AI Composer"
                  value={artistName}
                  onChange={(e) => setArtistName(e.target.value)}
                  data-testid="input-artist-name"
                  maxLength={100}
                  className="text-sm sm:text-base"
                />
                <p className="text-xs text-muted-foreground">
                  {artistName.length}/100 characters
                </p>
              </div>

              {/* Preview of request */}
              <div className="rounded-lg border bg-muted/30 p-2 sm:p-4 space-y-2">
                <p className="text-xs sm:text-sm font-medium text-muted-foreground">Preview:</p>
                <div className="space-y-1">
                  <p className="font-semibold text-sm sm:text-base text-foreground truncate">
                    {songName || "Song name..."}
                  </p>
                  <p className="text-xs sm:text-sm text-muted-foreground truncate">
                    {artistName || "Artist name..."}
                  </p>
                  {genre && (
                    <div className="flex items-center gap-2 mt-2 min-w-0">
                      <Music className="h-4 w-4 text-primary shrink-0" />
                      <p className="text-xs sm:text-sm text-foreground truncate min-w-0">
                        {(() => {
                          const [parentValue, childValue] = genre.split(":");
                          const parent = GENRES.find(g => g.value === parentValue);
                          if (!parent) return genre;

                          if (childValue && parent.children) {
                            const child = parent.children.find(c => c.value === childValue);
                            if (child) return `${parent.label} → ${child.label}`;
                          }

                          return parent.label;
                        })()}
                      </p>
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-lg border border-primary/20 bg-primary/5 p-2 sm:p-3">
                <p className="text-xs sm:text-sm text-muted-foreground flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary shrink-0" />
                  Get 30 votes and your song will be created and released!
                </p>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-col sm:flex-row justify-end gap-2 sm:gap-3 pt-3 sm:pt-4 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              data-testid="button-cancel-request"
              className="w-full sm:w-auto"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="lg"
              disabled={!songName.trim() || !artistName.trim() || !genre || !hasEnoughCredits}
              data-testid="button-submit-request"
              className="gap-2 w-full sm:w-auto"
            >
              <Coins className="h-4 w-4" />
              <span className="hidden sm:inline">Submit Request ({requestCost} credits)</span>
              <span className="sm:hidden">Submit ({requestCost} credits)</span>
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}