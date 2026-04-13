import { useState, useEffect } from 'react';
import { getSignedUrl } from '@/lib/s3Utils';
import type { Track } from '@shared/schema';

export interface SignedTrack extends Track {
  signedAudioUrl?: string;
  signedCoverUrl?: string;
}

/**
 * Hook to get signed URLs for a track's audio and cover image
 */
export function useSignedTrack(track: Track | null | undefined): SignedTrack | null {
  const [signedTrack, setSignedTrack] = useState<SignedTrack | null>(null);

  useEffect(() => {
    if (!track) {
      setSignedTrack(null);
      return;
    }

    let isMounted = true;

    async function loadSignedUrls() {
      if (!track) return;

      const [signedAudio, signedCover] = await Promise.all([
        track.audio_url ? getSignedUrl(track.audio_url) : Promise.resolve(track.audio_url),
        track.cover_image_url ? getSignedUrl(track.cover_image_url) : Promise.resolve(track.cover_image_url),
      ]);

      if (isMounted) {
        setSignedTrack({
          ...track,
          signedAudioUrl: signedAudio,
          signedCoverUrl: signedCover,
        });
      }
    }

    loadSignedUrls();

    return () => {
      isMounted = false;
    };
  }, [track?.id, track?.audio_url, track?.cover_image_url]);

  return signedTrack;
}

/**
 * Hook to get signed URLs for multiple tracks
 */
export function useSignedTracks(tracks: Track[] | undefined): SignedTrack[] {
  const [signedTracks, setSignedTracks] = useState<SignedTrack[]>([]);

  // Create a stable dependency using track IDs and URLs to detect changes
  const trackKey = tracks?.map(t => `${t.id}:${t.audio_url}:${t.cover_image_url}`).join('|') || '';

  useEffect(() => {
    if (!tracks || tracks.length === 0) {
      setSignedTracks([]);
      return;
    }

    let isMounted = true;

    async function loadSignedUrls() {
      if (!tracks) return;

      const signed = await Promise.all(
        tracks.map(async (track) => {
          const [signedAudio, signedCover] = await Promise.all([
            track.audio_url ? getSignedUrl(track.audio_url) : Promise.resolve(track.audio_url),
            track.cover_image_url ? getSignedUrl(track.cover_image_url) : Promise.resolve(track.cover_image_url),
          ]);

          return {
            ...track,
            signedAudioUrl: signedAudio,
            signedCoverUrl: signedCover,
          };
        })
      );

      if (isMounted) {
        setSignedTracks(signed);
      }
    }

    loadSignedUrls();

    return () => {
      isMounted = false;
    };
  }, [trackKey]); // Only depend on trackKey, tracks is accessed via closure

  return signedTracks;
}

/**
 * Transform a track with signed URLs into a format for the music player
 */
export function transformSignedTrackForPlayer(track: SignedTrack) {
  // Generate thumbnail URL with signed URL if available, otherwise use original
  const thumbnail = track.signedCoverUrl || track.cover_image_url || "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=400&h=400&fit=crop";

  return {
    id: track.id,
    title: track.title,
    artist: track.display_artist || track.artist || "Unknown Artist",
    thumbnail,
    audioUrl: track.signedAudioUrl || '', // Don't fallback to raw S3 URLs
    duration: formatDuration(track.duration_seconds),
    coverPosition: track.cover_position || "center center",
    genre: track.genre,
    streams: track.streams || 0,
  };
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}