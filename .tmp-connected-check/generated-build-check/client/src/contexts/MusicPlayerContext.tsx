import { createContext, useContext, useState, useRef, useEffect, ReactNode } from "react";
import { trackService } from "@/lib/trackService";
import { savedTrackService } from "@/lib/savedTrackService";
import { transformSignedTrackForPlayer } from "@/hooks/useSignedTrack";
import { getSignedUrl } from "@/lib/s3Utils";
import type { Track } from "@shared/schema";

interface Song {
  id: string;
  title: string;
  artist: string;
  thumbnail: string;
  audioUrl: string;
  duration: string;
  coverPosition?: string;
}

type PlayContext = 'explore' | 'library' | 'playlist' | null;

interface MusicPlayerContextType {
  currentSong: Song | null;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  playSong: (song: Song, context?: PlayContext) => void;
  playQueue: (songs: Song[], context?: PlayContext) => void;
  togglePlay: () => void;
  seekTo: (time: number) => void;
  playNext: () => void;
  playPrevious: () => void;
  canPlayNext: boolean;
  canPlayPrevious: boolean;
  audioRef: React.RefObject<HTMLAudioElement>;
}

const MusicPlayerContext = createContext<MusicPlayerContextType | undefined>(undefined);

export function MusicPlayerProvider({ children }: { children: ReactNode }) {
  const [currentSong, setCurrentSong] = useState<Song | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [queue, setQueue] = useState<Song[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [playHistory, setPlayHistory] = useState<Song[]>([]);
  const [playContext, setPlayContext] = useState<PlayContext>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  const addToHistory = () => {
    if (currentSong) {
      setPlayHistory(prev => [...prev, currentSong]);
    }
  };

  const playSong = (song: Song, context?: PlayContext) => {
    if (currentSong?.id === song.id) {
      // If same song, just toggle play/pause without reloading
      togglePlay();
    } else {
      // Add current song to history only when manually changing songs
      addToHistory();
      // New song, update current song and play
      setCurrentSong(song);
      setIsPlaying(true);
      setQueue([]);
      setCurrentIndex(0);
      // Update context - reset to null if not provided
      setPlayContext(context ?? null);
    }
  };

  const playQueue = (songs: Song[], context?: PlayContext) => {
    if (songs.length === 0) return;
    
    // Add current song to history when manually starting a queue
    addToHistory();
    
    setQueue(songs);
    setCurrentIndex(0);
    setCurrentSong(songs[0]);
    setIsPlaying(true);
    // Update context - reset to null if not provided
    setPlayContext(context ?? null);
  };

  const fetchAndPlayNextSong = async () => {
    try {
      let nextSong: Song | null = null;

      if (playContext === 'library') {
        // Fetch liked songs for the current user only
        const userStr = localStorage.getItem('user');
        const userId = userStr ? JSON.parse(userStr).id : null;
        
        if (!userId) {
          console.log('No user ID found for library auto-play');
          setIsPlaying(false);
          return;
        }

        // Fetch saved tracks scoped to current user only
        const savedTracks = await savedTrackService.getCurrent();
        const allTracks = await trackService.getAll();
        
        const savedTrackIds = new Set(savedTracks.map(st => st.track_id));
        const likedTracks = allTracks.filter(track => 
          savedTrackIds.has(track.id) && !track.is_deleted
        );
        
        if (likedTracks.length > 0) {
          // Find current song index
          const currentIndex = likedTracks.findIndex(t => t.id === currentSong?.id);
          // Get next song (or loop to first)
          const nextIndex = currentIndex >= 0 && currentIndex < likedTracks.length - 1
            ? currentIndex + 1
            : 0;
          const nextTrack = likedTracks[nextIndex];
          
          // Get signed URLs for track
          const [signedAudio, signedCover] = await Promise.all([
            nextTrack.audio_url ? getSignedUrl(nextTrack.audio_url) : Promise.resolve(''),
            nextTrack.cover_image_url ? getSignedUrl(nextTrack.cover_image_url) : Promise.resolve(''),
          ]);
          
          // Transform to player format with signed URLs
          const signedTrack = {
            ...nextTrack,
            signedAudioUrl: signedAudio,
            signedCoverUrl: signedCover,
          };
          nextSong = transformSignedTrackForPlayer(signedTrack);
        }
      } else {
        // Fetch random song from explore
        const allTracks = await trackService.getAll();
        const activeTracks = allTracks.filter(track => !track.is_deleted);
        
        if (activeTracks.length > 0) {
          // Pick a random track
          const randomIndex = Math.floor(Math.random() * activeTracks.length);
          const randomTrack = activeTracks[randomIndex];
          
          // Get signed URLs for track
          const [signedAudio, signedCover] = await Promise.all([
            randomTrack.audio_url ? getSignedUrl(randomTrack.audio_url) : Promise.resolve(''),
            randomTrack.cover_image_url ? getSignedUrl(randomTrack.cover_image_url) : Promise.resolve(''),
          ]);
          
          // Transform to player format with signed URLs
          const signedTrack = {
            ...randomTrack,
            signedAudioUrl: signedAudio,
            signedCoverUrl: signedCover,
          };
          nextSong = transformSignedTrackForPlayer(signedTrack);
        }
      }

      // Only add to history and update state if we successfully fetched a new song
      if (nextSong) {
        if (nextSong.id !== currentSong?.id) {
          // Different song - add to history and play
          addToHistory();
          setCurrentSong(nextSong);
          setIsPlaying(true);
        } else {
          // Same song (e.g., single-track library looping) - just replay without adding to history
          setCurrentSong(nextSong);
          setIsPlaying(true);
        }
      } else {
        // No next song available, stop playback
        setIsPlaying(false);
      }
    } catch (error) {
      console.log('Failed to fetch next song:', error);
      // Don't add to history on error
      setIsPlaying(false);
    }
  };

  const playNextInQueue = () => {
    if (queue.length > 0 && currentIndex < queue.length - 1) {
      // Add current song to history before advancing
      addToHistory();
      const nextIndex = currentIndex + 1;
      setCurrentIndex(nextIndex);
      setCurrentSong(queue[nextIndex]);
      setIsPlaying(true);
      return true;
    }
    return false;
  };

  const playNext = () => {
    // First try to play next in queue
    if (!playNextInQueue()) {
      // If no queue, fetch and play next song based on context
      fetchAndPlayNextSong();
    }
  };

  const playPrevious = () => {
    if (playHistory.length > 0) {
      const previousSong = playHistory[playHistory.length - 1];
      setPlayHistory(prev => prev.slice(0, -1));
      setCurrentSong(previousSong);
      setIsPlaying(true);
    }
  };

  const togglePlay = () => {
    if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      } else {
        const playPromise = audioRef.current.play();
        if (playPromise !== undefined) {
          playPromise
            .then(() => {
              setIsPlaying(true);
            })
            .catch((error) => {
              // Handle play interruption gracefully
              console.log('Playback prevented:', error);
              setIsPlaying(false);
            });
        }
      }
    }
  };

  const seekTo = (time: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = time;
      setCurrentTime(time);
    }
  };

  useEffect(() => {
    if (currentSong && audioRef.current) {
      // Only update src if it's different to prevent interruption
      if (audioRef.current.src !== currentSong.audioUrl) {
        audioRef.current.src = currentSong.audioUrl;
        
        // Increment streams when a new track starts loading
        trackService.incrementStreams(currentSong.id).catch((error) => {
          console.log('Failed to increment streams:', error);
        });
        
        if (isPlaying) {
          const playPromise = audioRef.current.play();
          if (playPromise !== undefined) {
            playPromise.catch((error) => {
              console.log('Playback prevented:', error);
              setIsPlaying(false);
            });
          }
        }
      } else if (isPlaying) {
        const playPromise = audioRef.current.play();
        if (playPromise !== undefined) {
          playPromise.catch((error) => {
            console.log('Playback prevented:', error);
            setIsPlaying(false);
          });
        }
      }
    }
  }, [currentSong, isPlaying]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const updateTime = () => setCurrentTime(audio.currentTime);
    const updateDuration = () => setDuration(audio.duration);
    const handleEnded = () => {
      playNext();
    };

    audio.addEventListener("timeupdate", updateTime);
    audio.addEventListener("loadedmetadata", updateDuration);
    audio.addEventListener("ended", handleEnded);

    return () => {
      audio.removeEventListener("timeupdate", updateTime);
      audio.removeEventListener("loadedmetadata", updateDuration);
      audio.removeEventListener("ended", handleEnded);
    };
  }, [queue, currentIndex]);

  const canPlayNext = queue.length > 0 && currentIndex < queue.length - 1 || playContext !== null;
  const canPlayPrevious = playHistory.length > 0;

  return (
    <MusicPlayerContext.Provider
      value={{
        currentSong,
        isPlaying,
        currentTime,
        duration,
        playSong,
        playQueue,
        togglePlay,
        seekTo,
        playNext,
        playPrevious,
        canPlayNext,
        canPlayPrevious,
        audioRef,
      }}
    >
      {children}
      <audio ref={audioRef} />
    </MusicPlayerContext.Provider>
  );
}

export function useMusicPlayer() {
  const context = useContext(MusicPlayerContext);
  if (context === undefined) {
    throw new Error("useMusicPlayer must be used within a MusicPlayerProvider");
  }
  return context;
}
