import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Upload, Music, Loader2, AlertCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface AdminUploadFormProps {
  onSubmit?: (data: {
    title: string;
    artist: string;
    thumbnail: string;
    audioUrl: string;
    duration: string;
  }) => void;
  isPending?: boolean;
  error?: Error | null;
}

export default function AdminUploadForm({ onSubmit, isPending, error }: AdminUploadFormProps) {
  const [formData, setFormData] = useState({
    title: "",
    artist: "",
    thumbnail: "",
    audioUrl: "",
    duration: "",
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (Object.values(formData).every((value) => value.trim())) {
      onSubmit?.(formData);
      setFormData({
        title: "",
        artist: "",
        thumbnail: "",
        audioUrl: "",
        duration: "",
      });
    }
  };

  const handleChange = (field: string, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const isValid = Object.values(formData).every((value) => value.trim());

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Upload className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">Upload New Song</h2>
            <p className="text-sm text-muted-foreground">Add a new AI-generated track</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="title">Song Title</Label>
            <Input
              id="title"
              placeholder="e.g., Neon Dreams"
              value={formData.title}
              onChange={(e) => handleChange("title", e.target.value)}
              data-testid="input-song-title"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="artist">Artist Name</Label>
            <Input
              id="artist"
              placeholder="e.g., AI Composer"
              value={formData.artist}
              onChange={(e) => handleChange("artist", e.target.value)}
              data-testid="input-artist"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="thumbnail">Thumbnail URL</Label>
            <Input
              id="thumbnail"
              placeholder="https://example.com/image.jpg"
              value={formData.thumbnail}
              onChange={(e) => handleChange("thumbnail", e.target.value)}
              data-testid="input-thumbnail"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="audioUrl">Audio URL</Label>
            <Input
              id="audioUrl"
              placeholder="https://example.com/audio.mp3"
              value={formData.audioUrl}
              onChange={(e) => handleChange("audioUrl", e.target.value)}
              data-testid="input-audio-url"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="duration">Duration (mm:ss)</Label>
            <Input
              id="duration"
              placeholder="e.g., 3:24"
              value={formData.duration}
              onChange={(e) => handleChange("duration", e.target.value)}
              data-testid="input-duration"
            />
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {error.message}
              </AlertDescription>
            </Alert>
          )}

          <Button
            type="submit"
            className="w-full"
            disabled={!isValid || isPending}
            data-testid="button-upload-song"
          >
            {isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload className="h-4 w-4 mr-2" />
                Upload Song
              </>
            )}
          </Button>
        </form>
      </Card>

      <Card className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Music className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">Preview</h2>
            <p className="text-sm text-muted-foreground">How your song will appear</p>
          </div>
        </div>

        {formData.thumbnail ? (
          <div className="relative aspect-square rounded-lg overflow-hidden mb-4">
            <img
              src={formData.thumbnail}
              alt="Preview"
              className="h-full w-full object-cover"
            />
          </div>
        ) : (
          <div className="relative aspect-square rounded-lg overflow-hidden mb-4 bg-secondary flex items-center justify-center">
            <Music className="h-12 w-12 text-muted-foreground" />
          </div>
        )}

        <div className="space-y-2">
          <h3 className="font-medium text-foreground">
            {formData.title || "Song Title"}
          </h3>
          <p className="text-sm text-muted-foreground">
            {formData.artist || "Artist Name"}
          </p>
          {formData.duration && (
            <p className="text-xs text-muted-foreground">
              Duration: {formData.duration}
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}
