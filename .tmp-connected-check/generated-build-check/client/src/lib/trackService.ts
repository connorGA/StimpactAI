// Track Service for Xano
import { xanoApi } from './xanoClient';
import type { Track, InsertTrack } from '@shared/schema';

const API_BASE = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';
const BASE_PATH = '/track';

export interface UpdateTrackInput {
  title?: string;
  display_artist?: string;
  duration_seconds?: number;
  bpm?: number;
  musical_key?: string;
  loudness_lufs?: number;
  cover_image_url?: string;
  audio_url?: string;
  preview_url?: string;
  waveform_json_url?: string;
  release_date?: string;
  provider?: string;
  prompt_text?: string;
  seed?: number;
  rights_status?: string;
  updated_at?: number;
  is_deleted?: boolean;
  streams?: number;
  last_streamed_at?: number;
  track_id: string;
}

/**
 * Get all tracks
 * GET /track
 */
export async function getAllTracks(): Promise<Track[]> {
  return xanoApi.get<Track[]>(`${API_BASE}${BASE_PATH}`);
}

/**
 * Get a single track by ID
 * GET /track/{track_id}
 */
export async function getTrack(id: string): Promise<Track> {
  return xanoApi.get<Track>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Create a new track
 * POST /track
 */
export async function createTrack(data: InsertTrack): Promise<Track> {
  return xanoApi.post<Track>(`${API_BASE}${BASE_PATH}`, data);
}

/**
 * Update a track
 * PATCH /track/{track_id}
 */
export async function updateTrack(
  id: string,
  data: UpdateTrackInput
): Promise<Track> {
  return xanoApi.patch<Track>(`${API_BASE}${BASE_PATH}/${id}`, {
    ...data,
    track_id: id,
  });
}

/**
 * Delete a track
 * DELETE /track/{track_id}
 */
export async function deleteTrack(id: string): Promise<void> {
  return xanoApi.delete<void>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Increment streams for a track
 * This fetches the current track, increments streams, and updates it
 */
export async function incrementStreams(id: string): Promise<Track> {
  // First, get the current track data
  const track = await xanoApi.get<Track>(`${API_BASE}${BASE_PATH}/${id}`);
  
  // Increment streams and update last_streamed_at
  const updatedData: UpdateTrackInput = {
    track_id: id,
    streams: (track.streams || 0) + 1,
    last_streamed_at: Date.now(),
    updated_at: Date.now(),
  };
  
  // Update the track with new streams count
  return xanoApi.patch<Track>(`${API_BASE}${BASE_PATH}/${id}`, updatedData);
}

export const trackService = {
  getAll: getAllTracks,
  getOne: getTrack,
  create: createTrack,
  update: updateTrack,
  delete: deleteTrack,
  incrementStreams: incrementStreams,
};
