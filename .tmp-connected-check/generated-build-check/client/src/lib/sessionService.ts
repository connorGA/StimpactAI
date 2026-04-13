// Session Service for Xano
import { xanoApi } from './xanoClient';
import type { Session } from '@shared/schema';

const API_BASE = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';
const BASE_PATH = '/session';

export interface CreateSessionInput {
  token_hash: string;
  expires_at: number;
  user_id: string;
}

export interface UpdateSessionInput {
  token_hash?: string;
  expires_at?: number;
  user_id?: string;
  session_id: string;
}

/**
 * Get all sessions
 * GET /session
 */
export async function getAllSessions(): Promise<Session[]> {
  return xanoApi.get<Session[]>(`${API_BASE}${BASE_PATH}`);
}

/**
 * Get a single session by ID
 * GET /session/{session_id}
 */
export async function getSession(id: string): Promise<Session> {
  return xanoApi.get<Session>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Create a new session
 * POST /session
 */
export async function createSession(
  data: CreateSessionInput
): Promise<Session> {
  return xanoApi.post<Session>(`${API_BASE}${BASE_PATH}`, data);
}

/**
 * Update a session
 * PATCH /session/{session_id}
 */
export async function updateSession(
  id: string,
  data: UpdateSessionInput
): Promise<Session> {
  return xanoApi.patch<Session>(`${API_BASE}${BASE_PATH}/${id}`, {
    ...data,
    session_id: id,
  });
}

/**
 * Delete a session
 * DELETE /session/{session_id}
 */
export async function deleteSession(id: string): Promise<void> {
  return xanoApi.delete<void>(`${API_BASE}${BASE_PATH}/${id}`);
}

export const sessionService = {
  getAll: getAllSessions,
  getOne: getSession,
  create: createSession,
  update: updateSession,
  delete: deleteSession,
};
