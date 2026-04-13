
import { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import { Upload, Music2, Image as ImageIcon, Loader2, Music } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { trackService } from "@/lib/trackService";
import { queryClient } from "@/lib/queryClient";
import GenreWheel from "@/components/GenreWheel";
import type { InsertTrack } from "@shared/schema";
import { usePlanLimits } from "@/hooks/usePlanLimits";
import { useAuth } from "@/contexts/AuthContext";
import { useLocation } from "wouter";
import { getAuthToken } from "@/lib/xanoClient";

const createTrackSchema = z.object({
  title: z.string().min(1, "Title is required"),
  artist: z.string().min(1, "Artist is required"),
  duration: z.string().regex(/^\d+:\d{2}$/, "Duration must be in MM:SS format"),
  genre: z.string().min(1, "Genre is required"),
});

type CreateTrackInput = z.infer<typeof createTrackSchema>;

export default function Create() {
  const { toast } = useToast();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { planTier, isLoading: planLoading } = usePlanLimits();
  const [, navigate] = useLocation();
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string>("");
  const [coverUrl, setCoverUrl] = useState<string>("");
  const [coverPosition, setCoverPosition] = useState<string>("center center");
  const [uploadingAudio, setUploadingAudio] = useState(false);
  const [uploadingCover, setUploadingCover] = useState(false);

  // Redirect non-admin users
  useEffect(() => {
    if (authLoading || planLoading) {
      return;
    }

    if (!isAuthenticated) {
      toast({
        title: "Authentication required",
        description: "Please log in to access this page",
        variant: "destructive",
      });
      navigate("/login");
    } else if (planTier !== 'admin') {
      toast({
        title: "Access denied",
        description: "This page is only accessible to administrators",
        variant: "destructive",
      });
      navigate("/");
    }
  }, [isAuthenticated, authLoading, planTier, planLoading, navigate, toast]);

  const form = useForm<CreateTrackInput>({
    resolver: zodResolver(createTrackSchema),
    defaultValues: {
      title: "",
      artist: "",
      duration: "",
      genre: "",
    },
  });

  // Upload audio file
  const uploadAudio = async (file: File) => {
    setUploadingAudio(true);
    try {
      const token = getAuthToken();
      if (!token) {
        throw new Error('Authentication required');
      }

      const formData = new FormData();
      formData.append('audio', file);

      const response = await fetch('/api/upload/audio', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to upload audio file');
      }

      const data = await response.json();
      setAudioUrl(data.url);
      toast({
        title: "Audio uploaded",
        description: "Audio file uploaded successfully",
      });
    } catch (error) {
      toast({
        title: "Upload failed",
        description: error instanceof Error ? error.message : "Failed to upload audio",
        variant: "destructive",
      });
    } finally {
      setUploadingAudio(false);
    }
  };

  // Upload cover art
  const uploadCover = async (file: File) => {
    setUploadingCover(true);
    try {
      const token = getAuthToken();
      if (!token) {
        throw new Error('Authentication required');
      }

      const formData = new FormData();
      formData.append('cover', file);

      const response = await fetch('/api/upload/cover', {
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
      setCoverUrl(data.url);
      toast({
        title: "Cover uploaded",
        description: "Cover image uploaded successfully",
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

  // Create track mutation
  const createTrackMutation = useMutation({
    mutationFn: async (data: CreateTrackInput) => {
      if (!audioUrl) {
        throw new Error("Please upload an audio file first");
      }

      // Convert duration from "MM:SS" to seconds
      const [mins, secs] = data.duration.split(':').map(Number);
      const durationSeconds = (mins * 60) + secs;

      const trackData: InsertTrack = {
        title: data.title,
        artist: data.artist,
        genre: data.genre,
        display_artist: data.artist,
        duration_seconds: durationSeconds,
        audio_url: audioUrl,
        cover_image_url: coverUrl || undefined,
        cover_position: coverUrl ? coverPosition : undefined,
        updated_at: Math.floor(Date.now() / 1000),
        is_deleted: false,
        release_date: new Date().toISOString(),
      };

      return trackService.create(trackData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/tracks'] });
      toast({
        title: "Track Created Successfully",
        description: `"${form.getValues('title')}" by ${form.getValues('artist')} has been published to the platform`,
      });
      // Reset form
      form.reset();
      setAudioFile(null);
      setCoverFile(null);
      setAudioUrl("");
      setCoverUrl("");
      setCoverPosition("center center");
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to publish",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const onSubmit = (data: CreateTrackInput) => {
    createTrackMutation.mutate(data);
  };

  // Show loading state while checking access
  if (authLoading || planLoading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-3 sm:px-6 py-4 sm:py-8 max-w-7xl">
          <div className="flex items-center justify-center min-h-[400px]">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        </div>
      </div>
    );
  }

  const watchedValues = form.watch();
  const previewThumbnail = coverUrl || "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=400&h=400&fit=crop";

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-3 sm:px-6 py-4 sm:py-8 max-w-7xl">
        <div className="mb-6 sm:mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
              <Upload className="h-6 w-6 text-primary" />
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-foreground">Create Track</h1>
          </div>
          <p className="text-sm sm:text-base text-muted-foreground">Upload and publish new tracks to the platform</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
          {/* Form Section */}
          <div className="space-y-6">
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              {/* Audio Upload */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Music2 className="h-5 w-5" />
                    Audio File
                  </CardTitle>
                  <CardDescription>Upload the audio file for your track (MP3, WAV, etc.)</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <Input
                      type="file"
                      accept="audio/*"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setAudioFile(file);
                          uploadAudio(file);
                        }
                      }}
                      disabled={uploadingAudio}
                      data-testid="input-audio-file"
                    />
                    {uploadingAudio && (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Uploading audio...
                      </div>
                    )}
                    {audioFile && !uploadingAudio && (
                      <div className="text-sm text-green-600 dark:text-green-400">
                        ✓ {audioFile.name} uploaded
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Cover Art Upload */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ImageIcon className="h-5 w-5" />
                    Cover Art (Optional)
                  </CardTitle>
                  <CardDescription>Upload a cover image for your track</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <Input
                      type="file"
                      accept="image/*"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setCoverFile(file);
                          uploadCover(file);
                        }
                      }}
                      disabled={uploadingCover}
                      data-testid="input-cover-file"
                    />
                    {uploadingCover && (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Uploading cover...
                      </div>
                    )}
                    {coverFile && !uploadingCover && (
                      <div className="text-sm text-green-600 dark:text-green-400">
                        ✓ {coverFile.name} uploaded
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Track Details */}
              <Card>
                <CardHeader>
                  <CardTitle>Track Details</CardTitle>
                  <CardDescription>Enter the details for your track</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="title">Title</Label>
                    <Input
                      id="title"
                      {...form.register("title")}
                      placeholder="Track title"
                      data-testid="input-title"
                    />
                    {form.formState.errors.title && (
                      <p className="text-sm text-destructive">{form.formState.errors.title.message}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="artist">Artist</Label>
                    <Input
                      id="artist"
                      {...form.register("artist")}
                      placeholder="Artist name"
                      data-testid="input-artist"
                    />
                    {form.formState.errors.artist && (
                      <p className="text-sm text-destructive">{form.formState.errors.artist.message}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="duration">Duration (MM:SS)</Label>
                    <Input
                      id="duration"
                      {...form.register("duration")}
                      placeholder="3:45"
                      data-testid="input-duration"
                    />
                    {form.formState.errors.duration && (
                      <p className="text-sm text-destructive">{form.formState.errors.duration.message}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label>Genre</Label>
                    <GenreWheel
                      value={form.watch("genre")}
                      onValueChange={(value) => form.setValue("genre", value)}
                    />
                    {form.formState.errors.genre && (
                      <p className="text-sm text-destructive">{form.formState.errors.genre.message}</p>
                    )}
                  </div>
                </CardContent>
              </Card>

              <Button
                type="submit"
                size="lg"
                className="w-full"
                disabled={createTrackMutation.isPending || uploadingAudio || uploadingCover || !audioUrl}
                data-testid="button-publish-track"
              >
                {createTrackMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Publishing...
                  </>
                ) : (
                  <>
                    <Upload className="mr-2 h-4 w-4" />
                    Publish Track
                  </>
                )}
              </Button>
            </form>
          </div>

          {/* Preview Section */}
          <div className="lg:sticky lg:top-8 lg:self-start">
            <Card className="p-4 sm:p-6">
              <div className="flex items-center gap-3 mb-4 sm:mb-6">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                  <Music className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h2 className="text-base sm:text-lg font-semibold text-foreground">Preview</h2>
                  <p className="text-xs sm:text-sm text-muted-foreground">How your track will appear</p>
                </div>
              </div>

              <div className="relative aspect-square rounded-lg overflow-hidden mb-4 group">
                <img
                  src={previewThumbnail}
                  alt="Preview"
                  className="h-full w-full object-cover cursor-move"
                  style={{ objectPosition: coverPosition }}
                  draggable="false"
                  onMouseDown={(e) => {
                    if (!coverUrl) return;
                    const img = e.currentTarget;
                    const rect = img.getBoundingClientRect();
                    const startX = e.clientX;
                    const startY = e.clientY;
                    
                    // Parse current position
                    const [currentX, currentY] = coverPosition.split(' ');
                    const startPosX = currentX.includes('%') ? parseFloat(currentX) : 50;
                    const startPosY = currentY.includes('%') ? parseFloat(currentY) : 50;

                    const handleMouseMove = (moveEvent: MouseEvent) => {
                      const deltaX = moveEvent.clientX - startX;
                      const deltaY = moveEvent.clientY - startY;
                      
                      // Convert delta to percentage
                      const percentX = (deltaX / rect.width) * 100;
                      const percentY = (deltaY / rect.height) * 100;
                      
                      const newX = Math.max(0, Math.min(100, startPosX + percentX));
                      const newY = Math.max(0, Math.min(100, startPosY + percentY));
                      
                      setCoverPosition(`${newX}% ${newY}%`);
                    };

                    const handleMouseUp = () => {
                      document.removeEventListener('mousemove', handleMouseMove);
                      document.removeEventListener('mouseup', handleMouseUp);
                    };

                    document.addEventListener('mousemove', handleMouseMove);
                    document.addEventListener('mouseup', handleMouseUp);
                  }}
                />
                {coverUrl && (
                  <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setCoverPosition("center center")}
                    >
                      Reset Position
                    </Button>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <h3 className="font-medium text-foreground">
                  {watchedValues.title || "Track Title"}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {watchedValues.artist || "Artist Name"}
                </p>
                {watchedValues.duration && (
                  <p className="text-xs text-muted-foreground">
                    Duration: {watchedValues.duration}
                  </p>
                )}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
