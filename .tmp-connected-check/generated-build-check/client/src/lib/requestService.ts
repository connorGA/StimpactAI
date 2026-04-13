// Request Service for Xano
import { xanoApi } from './xanoClient';
import type { Request, InsertRequest } from '@shared/schema';

const API_BASE = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';
const BASE_PATH = '/requests';

export interface UpdateRequestInput {
  title?: string;
  artist?: string;
  genre?: string;
  description?: string;
  votes?: number;
  released?: boolean;
  release_date?: number;
  requests_id: string;
}

/**
 * Get all requests
 * GET /requests
 */
export async function getAllRequests(): Promise<Request[]> {
  return xanoApi.get<Request[]>(`${API_BASE}${BASE_PATH}`);
}

/**
 * Get a single request by ID
 * GET /requests/{requests_id}
 */
export async function getRequest(id: string): Promise<Request> {
  return xanoApi.get<Request>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Create a new request
 * POST /requests
 */
export async function createRequest(data: InsertRequest): Promise<Request> {
  return xanoApi.post<Request>(`${API_BASE}${BASE_PATH}`, data);
}

/**
 * Update a request
 * PATCH /requests/{requests_id}
 */
export async function updateRequest(
  id: string,
  data: UpdateRequestInput
): Promise<Request> {
  return xanoApi.patch<Request>(`${API_BASE}${BASE_PATH}/${id}`, {
    ...data,
    requests_id: id,
  });
}

/**
 * Delete a request
 * DELETE /requests/{requests_id}
 */
export async function deleteRequest(id: string): Promise<void> {
  return xanoApi.delete<void>(`${API_BASE}${BASE_PATH}/${id}`);
}

export const requestService = {
  getAll: getAllRequests,
  getOne: getRequest,
  create: createRequest,
  update: updateRequest,
  delete: deleteRequest,
};
