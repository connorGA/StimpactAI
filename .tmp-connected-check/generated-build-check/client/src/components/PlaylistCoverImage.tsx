import { useEffect, useState } from "react";
import { getSignedUrl } from "@/lib/s3Utils";
import type { Track } from "@shared/schema";
import defaultPlaylistCover from "@assets/default-playlist-cover.png";

interface PlaylistCoverImageProps {
  coverImageUrl?: string;
  tracks: Track[];
  playlistName: string;
  className?: string;
}

export default function PlaylistCoverImage({
  coverImageUrl,
  tracks,
  playlistName,
  className = "",
}: PlaylistCoverImageProps) {
  const [signedCoverUrl, setSignedCoverUrl] = useState<string>("");
  const [signedTrackCovers, setSignedTrackCovers] = useState<string[]>([]);

  useEffect(() => {
    async function loadSignedUrls() {
      if (coverImageUrl) {
        const signed = await getSignedUrl(coverImageUrl);
        setSignedCoverUrl(signed);
        setSignedTrackCovers([]);
      } else {
        setSignedCoverUrl("");
        
        if (tracks.length > 0) {
          const firstFourTracks = tracks.slice(0, 4);
          const signedUrls = await Promise.all(
            firstFourTracks.map(async (track) => {
              if (track.cover_image_url) {
                return await getSignedUrl(track.cover_image_url);
              }
              return "";
            })
          );
          setSignedTrackCovers(signedUrls.filter(url => url !== ""));
        } else {
          setSignedTrackCovers([]);
        }
      }
    }

    loadSignedUrls();
  }, [coverImageUrl, tracks]);

  if (signedCoverUrl) {
    return (
      <img
        src={signedCoverUrl}
        alt={playlistName}
        className={className}
        data-testid="img-playlist-custom-cover"
      />
    );
  }

  if (signedTrackCovers.length === 0) {
    return (
      <img
        src={defaultPlaylistCover}
        alt={playlistName}
        className={className}
        data-testid="img-playlist-default-cover"
      />
    );
  }

  if (signedTrackCovers.length === 1) {
    return (
      <img
        src={signedTrackCovers[0]}
        alt={playlistName}
        className={className}
        data-testid="img-playlist-single-track-cover"
      />
    );
  }

  if (signedTrackCovers.length === 2) {
    return (
      <div className={`grid grid-cols-2 ${className}`} data-testid="div-playlist-two-track-mosaic">
        <img
          src={signedTrackCovers[0]}
          alt={`${playlistName} track 1`}
          className="h-full w-full object-cover"
        />
        <img
          src={signedTrackCovers[1]}
          alt={`${playlistName} track 2`}
          className="h-full w-full object-cover"
        />
      </div>
    );
  }

  if (signedTrackCovers.length === 3) {
    return (
      <div className={`grid grid-cols-2 grid-rows-2 ${className}`} data-testid="div-playlist-three-track-mosaic">
        <img
          src={signedTrackCovers[0]}
          alt={`${playlistName} track 1`}
          className="h-full w-full object-cover row-span-2"
        />
        <img
          src={signedTrackCovers[1]}
          alt={`${playlistName} track 2`}
          className="h-full w-full object-cover"
        />
        <img
          src={signedTrackCovers[2]}
          alt={`${playlistName} track 3`}
          className="h-full w-full object-cover"
        />
      </div>
    );
  }

  return (
    <div className={`grid grid-cols-2 grid-rows-2 ${className}`} data-testid="div-playlist-four-track-mosaic">
      <img
        src={signedTrackCovers[0]}
        alt={`${playlistName} track 1`}
        className="h-full w-full object-cover"
      />
      <img
        src={signedTrackCovers[1]}
        alt={`${playlistName} track 2`}
        className="h-full w-full object-cover"
      />
      <img
        src={signedTrackCovers[2]}
        alt={`${playlistName} track 3`}
        className="h-full w-full object-cover"
      />
      <img
        src={signedTrackCovers[3]}
        alt={`${playlistName} track 4`}
        className="h-full w-full object-cover"
      />
    </div>
  );
}
