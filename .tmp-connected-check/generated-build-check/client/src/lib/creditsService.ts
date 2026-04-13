// Credits Service for Xano
import { xanoApi } from './xanoClient';
import type { Credits, InsertCredits } from '@shared/schema';

const BASE_PATH = '/credits';

export interface UpdateCreditsInput {
  user_id?: string;
  credits?: number;
  last_spend?: number;
  last_refilled?: number;
  credits_id: string;
}

/**
 * Get all credits
 * GET /credits
 */
export async function getAllCredits(): Promise<Credits[]> {
  return xanoApi.get<Credits[]>(BASE_PATH);
}

/**
 * Get credits by user ID
 * Fetches all credits and filters by user_id
 * @deprecated Use getCurrentUserCredits instead - this endpoint requires elevated privileges
 */
export async function getCreditsByUserId(userId: string): Promise<Credits | null> {
  const allCredits = await getAllCredits();
  const userCredits = allCredits.find(c => c.user_id === userId);
  return userCredits || null;
}

/**
 * Get current authenticated user's credits using server proxy
 * This endpoint uses server credentials to fetch credits
 * GET /api/credits/me
 */
export async function getCurrentUserCredits(): Promise<Credits | null> {
  const token = localStorage.getItem('xano_auth_token');
  
  const response = await fetch('/api/credits/me', {
    credentials: 'include',
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
    },
  });
  
  if (!response.ok) {
    if (response.status === 404) {
      return null;
    }
    throw new Error(`Failed to fetch credits: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Get a single credit record by ID
 * GET /credits/{credits_id}
 */
export async function getCredits(id: string): Promise<Credits> {
  return xanoApi.get<Credits>(`${BASE_PATH}/${id}`);
}

/**
 * Create a new credit record
 * POST /credits
 */
export async function createCredits(data: InsertCredits): Promise<Credits> {
  return xanoApi.post<Credits>(BASE_PATH, data);
}

/**
 * Update a credit record
 * PATCH /credits/{credits_id}
 */
export async function updateCredits(
  id: string,
  data: UpdateCreditsInput
): Promise<Credits> {
  return xanoApi.patch<Credits>(`${BASE_PATH}/${id}`, {
    ...data,
    credits_id: id,
  });
}

/**
 * Delete a credit record
 * DELETE /credits/{credits_id}
 */
export async function deleteCredits(id: string): Promise<void> {
  return xanoApi.delete<void>(`${BASE_PATH}/${id}`);
}

/**
 * Deduct credits from a user's account
 * Updates the credits and last_spend timestamp
 */
export async function deductCredits(
  creditsId: string,
  amount: number,
  currentCredits: number
): Promise<Credits> {
  const newCredits = currentCredits - amount;
  return updateCredits(creditsId, {
    credits: newCredits,
    last_spend: Date.now(),
    credits_id: creditsId,
  });
}

/**
 * Add credits to a user's account
 * Updates the credits and last_refilled timestamp
 */
export async function addCredits(
  creditsId: string,
  amount: number,
  currentCredits: number
): Promise<Credits> {
  const newCredits = currentCredits + amount;
  return updateCredits(creditsId, {
    credits: newCredits,
    last_refilled: Date.now(),
    credits_id: creditsId,
  });
}

export const creditsService = {
  getAll: getAllCredits,
  getByUserId: getCreditsByUserId,
  getCurrentUser: getCurrentUserCredits,
  getOne: getCredits,
  create: createCredits,
  update: updateCredits,
  delete: deleteCredits,
  deduct: deductCredits,
  add: addCredits,
};
