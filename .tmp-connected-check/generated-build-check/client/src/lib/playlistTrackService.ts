// Playlist Track Service for Xano
import { xanoApi } from './xanoClient';
import type { PlaylistTrack, InsertPlaylistTrack } from '@shared/schema';

const API_BASE = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';
const BASE_PATH = '/playlist_track';

export interface CreatePlaylistTrackInput {
  sort_index: number;
  added_at: number;
  playlist_id: string;
  track_id: string;
}

export interface UpdatePlaylistTrackInput {
  sort_index?: number;
  added_at?: number;
  playlist_id?: string;
  track_id?: string;
  playlist_track_id: string;
}

/**
 * Get all playlist tracks
 * GET /playlist_track
 */
export async function getAllPlaylistTracks(): Promise<PlaylistTrack[]> {
  return xanoApi.get<PlaylistTrack[]>(`${API_BASE}${BASE_PATH}`);
}

/**
 * Get playlist tracks for a specific playlist (direct Xano call - no auth check)
 * GET /playlist_track?playlist_id={playlistId}
 * @deprecated Use getPlaylistTracksByPlaylistIdSecure for user playlists
 */
export async function getPlaylistTracksByPlaylistId(playlistId: string): Promise<PlaylistTrack[]> {
  return xanoApi.get<PlaylistTrack[]>(`${API_BASE}${BASE_PATH}?playlist_id=${encodeURIComponent(playlistId)}`);
}

/**
 * Get playlist tracks with server-side ownership verification
 * GET /api/playlists/{playlistId}/tracks
 */
export async function getPlaylistTracksByPlaylistIdSecure(playlistId: string): Promise<PlaylistTrack[]> {
  const token = localStorage.getItem('xano_auth_token');
  const response = await fetch(`/api/playlists/${playlistId}/tracks`, {
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
    },
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to fetch playlist tracks');
  }
  
  return response.json();
}

/**
 * Get a single playlist track by ID
 * GET /playlist_track/{playlist_track_id}
 */
export async function getPlaylistTrack(id: string): Promise<PlaylistTrack> {
  return xanoApi.get<PlaylistTrack>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Create a new playlist track
 * POST /playlist_track
 */
export async function createPlaylistTrack(
  data: CreatePlaylistTrackInput
): Promise<PlaylistTrack> {
  return xanoApi.post<PlaylistTrack>(`${API_BASE}${BASE_PATH}`, data);
}

/**
 * Update a playlist track
 * PATCH /playlist_track/{playlist_track_id}
 */
export async function updatePlaylistTrack(
  id: string,
  data: UpdatePlaylistTrackInput
): Promise<PlaylistTrack> {
  return xanoApi.patch<PlaylistTrack>(`${API_BASE}${BASE_PATH}/${id}`, {
    ...data,
    playlist_track_id: id,
  });
}

/**
 * Delete a playlist track (direct Xano call - no auth check)
 * DELETE /playlist_track/{playlist_track_id}
 * @deprecated Use deletePlaylistTrackSecure for user playlists
 */
export async function deletePlaylistTrack(id: string): Promise<void> {
  return xanoApi.delete<void>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Delete a playlist track with server-side ownership verification
 * DELETE /api/playlists/{playlistId}/tracks/{trackId}
 * Note: This requires both playlistId and trackId
 */
export async function deletePlaylistTrackSecure(playlistId: string, trackId: string): Promise<void> {
  const token = localStorage.getItem('xano_auth_token');
  const response = await fetch(`/api/playlists/${playlistId}/tracks/${trackId}`, {
    method: 'DELETE',
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
    },
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to delete playlist track');
  }
}

export const playlistTrackService = {
  getAll: getAllPlaylistTracks,
  getByPlaylistId: getPlaylistTracksByPlaylistId,
  getByPlaylistIdSecure: getPlaylistTracksByPlaylistIdSecure,
  getOne: getPlaylistTrack,
  create: createPlaylistTrack,
  update: updatePlaylistTrack,
  delete: deletePlaylistTrack,
  deleteSecure: deletePlaylistTrackSecure,
};
