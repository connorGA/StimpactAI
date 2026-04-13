// Track Tag Service for Xano
import { xanoApi } from './xanoClient';
import type { TrackTag, InsertTrackTag } from '@shared/schema';

const API_BASE = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';
const BASE_PATH = '/track_tag';

export interface UpdateTrackTagInput {
  track_id?: string;
  tag_id?: string;
  track_tag_id: string;
}

/**
 * Get all track tags
 * GET /track_tag
 */
export async function getAllTrackTags(): Promise<TrackTag[]> {
  return xanoApi.get<TrackTag[]>(`${API_BASE}${BASE_PATH}`);
}

/**
 * Get a single track tag by ID
 * GET /track_tag/{track_tag_id}
 */
export async function getTrackTag(id: string): Promise<TrackTag> {
  return xanoApi.get<TrackTag>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Create a new track tag
 * POST /track_tag
 */
export async function createTrackTag(data: InsertTrackTag): Promise<TrackTag> {
  return xanoApi.post<TrackTag>(`${API_BASE}${BASE_PATH}`, data);
}

/**
 * Update a track tag
 * PATCH /track_tag/{track_tag_id}
 */
export async function updateTrackTag(
  id: string,
  data: UpdateTrackTagInput
): Promise<TrackTag> {
  return xanoApi.patch<TrackTag>(`${API_BASE}${BASE_PATH}/${id}`, {
    ...data,
    track_tag_id: id,
  });
}

/**
 * Delete a track tag
 * DELETE /track_tag/{track_tag_id}
 */
export async function deleteTrackTag(id: string): Promise<void> {
  return xanoApi.delete<void>(`${API_BASE}${BASE_PATH}/${id}`);
}

export const trackTagService = {
  getAll: getAllTrackTags,
  getOne: getTrackTag,
  create: createTrackTag,
  update: updateTrackTag,
  delete: deleteTrackTag,
};
