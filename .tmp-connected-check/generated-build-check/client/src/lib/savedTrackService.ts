// Saved Track Service for Xano
import { xanoApi } from './xanoClient';
import type { SavedTrack, InsertSavedTrack } from '@shared/schema';

const API_BASE = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';
const BASE_PATH = '/saved_track';

export interface UpdateSavedTrackInput {
  user_id?: string;
  track_id?: string;
  saved_track_id: string;
}

/**
 * Get all saved tracks (REMOVED - security risk)
 * This was removed because it fetched ALL users' saved tracks
 * @deprecated This endpoint has been removed for security reasons. Use getCurrentUserSavedTracks instead.
 */
export async function getAllSavedTracks(): Promise<SavedTrack[]> {
  throw new Error('getAllSavedTracks() is deprecated and disabled for security. Use getCurrentUserSavedTracks() instead.');
}

/**
 * Get current user's saved tracks via secure server proxy
 * GET /api/saved-tracks
 */
export async function getCurrentUserSavedTracks(): Promise<SavedTrack[]> {
  const token = localStorage.getItem('xano_auth_token');
  const response = await fetch('/api/saved-tracks', {
    method: 'GET',
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
    },
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to fetch saved tracks');
  }
  
  return response.json();
}

/**
 * Get saved tracks for a specific user (REMOVED - security risk)
 * @deprecated DISABLED for security. Use getCurrentUserSavedTracks() instead.
 */
export async function getSavedTracksByUserId(userId: string): Promise<SavedTrack[]> {
  throw new Error('getSavedTracksByUserId() is deprecated and disabled for security. Use getCurrent() instead.');
}

/**
 * Get a single saved track by ID
 * GET /saved_track/{saved_track_id}
 */
export async function getSavedTrack(id: string): Promise<SavedTrack> {
  return xanoApi.get<SavedTrack>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Create a new saved track
 * POST /saved_track
 */
export async function createSavedTrack(
  data: InsertSavedTrack
): Promise<SavedTrack> {
  return xanoApi.post<SavedTrack>(`${API_BASE}${BASE_PATH}`, data);
}

/**
 * Update a saved track
 * PATCH /saved_track/{saved_track_id}
 */
export async function updateSavedTrack(
  id: string,
  data: UpdateSavedTrackInput
): Promise<SavedTrack> {
  return xanoApi.patch<SavedTrack>(`${API_BASE}${BASE_PATH}/${id}`, {
    ...data,
    saved_track_id: id,
  });
}

/**
 * Delete a saved track
 * DELETE /saved_track/{saved_track_id}
 */
export async function deleteSavedTrack(id: string): Promise<void> {
  return xanoApi.delete<void>(`${API_BASE}${BASE_PATH}/${id}`);
}

export const savedTrackService = {
  getAll: getAllSavedTracks, // Throws error - use getCurrent instead
  getByUserId: getSavedTracksByUserId, // Deprecated - use getCurrent instead
  getCurrent: getCurrentUserSavedTracks,
  getOne: getSavedTrack,
  create: createSavedTrack,
  update: updateSavedTrack,
  delete: deleteSavedTrack,
};
