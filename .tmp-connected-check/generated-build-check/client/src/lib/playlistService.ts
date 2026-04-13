// Playlist Service for Xano
import { xanoApi } from './xanoClient';
import type { Playlist, InsertPlaylist } from '@shared/schema';

const API_BASE = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';
const BASE_PATH = '/playlist';

export interface UpdatePlaylistInput {
  name?: string;
  description?: string;
  cover_image_url?: string;
  privacy?: 'public' | 'private';
  updated_at?: number;
  is_deleted?: boolean;
  user_id?: string;
}

/**
 * Get current user's playlists via secure server proxy
 * GET /api/playlists (with auth token)
 */
export async function getCurrentUserPlaylists(): Promise<Playlist[]> {
  const token = localStorage.getItem('xano_auth_token');
  const response = await fetch('/api/playlists', {
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
    },
  });
  
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('Authentication required');
    }
    const error = await response.json();
    throw new Error(error.error || 'Failed to fetch playlists');
  }
  
  return response.json();
}

/**
 * Get all playlists (REMOVED - security risk)
 * @deprecated DISABLED for security. Use getCurrentUserPlaylists() instead.
 */
export async function getAllPlaylists(): Promise<Playlist[]> {
  throw new Error('getAllPlaylists() is deprecated and disabled for security. Use getCurrent() instead.');
}

/**
 * Get playlists for a specific user (REMOVED - security risk)
 * @deprecated DISABLED for security. Use getCurrentUserPlaylists() instead.
 */
export async function getPlaylistsByUserId(userId: string): Promise<Playlist[]> {
  throw new Error('getPlaylistsByUserId() is deprecated and disabled for security. Use getCurrent() instead.');
}

/**
 * Get a single playlist by ID (direct Xano call - no auth check)
 * GET /playlist/{playlist_id}
 * @deprecated Use getPlaylistSecure for user playlists
 */
export async function getPlaylist(id: string): Promise<Playlist> {
  return xanoApi.get<Playlist>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Get a single playlist by ID with server-side ownership verification
 * GET /api/playlists/{id}
 */
export async function getPlaylistSecure(id: string): Promise<Playlist> {
  const token = localStorage.getItem('xano_auth_token');
  const response = await fetch(`/api/playlists/${id}`, {
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
    },
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to fetch playlist');
  }
  
  return response.json();
}

/**
 * Create a new playlist
 * POST /playlist
 */
export async function createPlaylist(data: InsertPlaylist): Promise<Playlist> {
  return xanoApi.post<Playlist>(`${API_BASE}${BASE_PATH}`, data);
}

/**
 * Update a playlist (direct Xano call - no auth check)
 * PATCH /playlist/{playlist_id}
 * @deprecated Use updatePlaylistSecure for user playlists
 */
export async function updatePlaylist(
  id: string,
  data: UpdatePlaylistInput
): Promise<Playlist> {
  return xanoApi.patch<Playlist>(`${API_BASE}${BASE_PATH}/${id}`, data);
}

/**
 * Update a playlist with server-side ownership verification
 * PATCH /api/playlists/{id}
 */
export async function updatePlaylistSecure(
  id: string,
  data: UpdatePlaylistInput
): Promise<Playlist> {
  const token = localStorage.getItem('xano_auth_token');
  const response = await fetch(`/api/playlists/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': token ? `Bearer ${token}` : '',
    },
    body: JSON.stringify(data),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to update playlist');
  }
  
  return response.json();
}

/**
 * Delete a playlist (direct Xano call - no auth check)
 * DELETE /playlist/{playlist_id}
 * @deprecated Use deletePlaylistSecure for user playlists
 */
export async function deletePlaylist(id: string): Promise<void> {
  return xanoApi.delete<void>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Delete a playlist with server-side ownership verification
 * DELETE /api/playlists/{id}
 */
export async function deletePlaylistSecure(id: string): Promise<void> {
  const token = localStorage.getItem('xano_auth_token');
  const response = await fetch(`/api/playlists/${id}`, {
    method: 'DELETE',
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
    },
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to delete playlist');
  }
}

export const playlistService = {
  getCurrent: getCurrentUserPlaylists,
  getAll: getAllPlaylists,
  getByUserId: getPlaylistsByUserId,
  getOne: getPlaylist,
  getOneSecure: getPlaylistSecure,
  create: createPlaylist,
  update: updatePlaylist,
  updateSecure: updatePlaylistSecure,
  delete: deletePlaylist,
  deleteSecure: deletePlaylistSecure,
};
