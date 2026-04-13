// Playback Event Service for Xano
import { xanoApi } from './xanoClient';
import type { PlaybackEvent, InsertPlaybackEvent } from '@shared/schema';

const API_BASE = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';
const BASE_PATH = '/playback_event';

/**
 * Get all playback events
 * GET /playback_event
 */
export async function getAllPlaybackEvents(): Promise<PlaybackEvent[]> {
  return xanoApi.get<PlaybackEvent[]>(`${API_BASE}${BASE_PATH}`);
}

/**
 * Get a single playback event by ID
 * GET /playback_event/{playback_event_id}
 */
export async function getPlaybackEvent(id: string): Promise<PlaybackEvent> {
  return xanoApi.get<PlaybackEvent>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Create a new playback event
 * POST /playback_event
 */
export async function createPlaybackEvent(
  data: InsertPlaybackEvent
): Promise<PlaybackEvent> {
  return xanoApi.post<PlaybackEvent>(`${API_BASE}${BASE_PATH}`, data);
}

/**
 * Update a playback event
 * PATCH /playback_event/{playback_event_id}
 */
export async function updatePlaybackEvent(
  id: string,
  data: Partial<InsertPlaybackEvent>
): Promise<PlaybackEvent> {
  return xanoApi.patch<PlaybackEvent>(`${API_BASE}${BASE_PATH}/${id}`, data);
}

/**
 * Delete a playback event
 * DELETE /playback_event/{playback_event_id}
 */
export async function deletePlaybackEvent(id: string): Promise<void> {
  return xanoApi.delete<void>(`${API_BASE}${BASE_PATH}/${id}`);
}

export const playbackService = {
  getAll: getAllPlaybackEvents,
  getOne: getPlaybackEvent,
  create: createPlaybackEvent,
  update: updatePlaybackEvent,
  delete: deletePlaybackEvent,
};
