// Moderation Event Service for Xano
import { xanoApi } from './xanoClient';
import type { ModerationEvent, InsertModerationEvent } from '@shared/schema';

const API_BASE = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';
const BASE_PATH = '/moderation_event';

/**
 * Get all moderation events
 * GET /moderation_event
 */
export async function getAllModerationEvents(): Promise<ModerationEvent[]> {
  return xanoApi.get<ModerationEvent[]>(`${API_BASE}${BASE_PATH}`);
}

/**
 * Get a single moderation event by ID
 * GET /moderation_event/{moderation_event_id}
 */
export async function getModerationEvent(id: string): Promise<ModerationEvent> {
  return xanoApi.get<ModerationEvent>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Create a new moderation event
 * POST /moderation_event
 */
export async function createModerationEvent(
  data: InsertModerationEvent
): Promise<ModerationEvent> {
  return xanoApi.post<ModerationEvent>(`${API_BASE}${BASE_PATH}`, data);
}

/**
 * Update a moderation event
 * PATCH /moderation_event/{moderation_event_id}
 */
export async function updateModerationEvent(
  id: string,
  data: Partial<InsertModerationEvent>
): Promise<ModerationEvent> {
  return xanoApi.patch<ModerationEvent>(`${API_BASE}${BASE_PATH}/${id}`, data);
}

/**
 * Delete a moderation event
 * DELETE /moderation_event/{moderation_event_id}
 */
export async function deleteModerationEvent(id: string): Promise<void> {
  return xanoApi.delete<void>(`${API_BASE}${BASE_PATH}/${id}`);
}

export const moderationService = {
  getAll: getAllModerationEvents,
  getOne: getModerationEvent,
  create: createModerationEvent,
  update: updateModerationEvent,
  delete: deleteModerationEvent,
};
