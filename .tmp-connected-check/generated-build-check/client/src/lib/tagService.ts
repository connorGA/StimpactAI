// Tag Service for Xano
import { xanoApi } from './xanoClient';
import type { Tag, InsertTag } from '@shared/schema';

const API_BASE = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';
const BASE_PATH = '/tag';

export interface UpdateTagInput {
  type?: string;
  name?: string;
  tag_id: string;
}

/**
 * Get all tags
 * GET /tag
 */
export async function getAllTags(): Promise<Tag[]> {
  return xanoApi.get<Tag[]>(`${API_BASE}${BASE_PATH}`);
}

/**
 * Get a single tag by ID
 * GET /tag/{tag_id}
 */
export async function getTag(id: string): Promise<Tag> {
  return xanoApi.get<Tag>(`${API_BASE}${BASE_PATH}/${id}`);
}

/**
 * Create a new tag
 * POST /tag
 */
export async function createTag(data: InsertTag): Promise<Tag> {
  return xanoApi.post<Tag>(`${API_BASE}${BASE_PATH}`, data);
}

/**
 * Update a tag
 * PATCH /tag/{tag_id}
 */
export async function updateTag(
  id: string,
  data: UpdateTagInput
): Promise<Tag> {
  return xanoApi.patch<Tag>(`${API_BASE}${BASE_PATH}/${id}`, {
    ...data,
    tag_id: id,
  });
}

/**
 * Delete a tag
 * DELETE /tag/{tag_id}
 */
export async function deleteTag(id: string): Promise<void> {
  return xanoApi.delete<void>(`${API_BASE}${BASE_PATH}/${id}`);
}

export const tagService = {
  getAll: getAllTags,
  getOne: getTag,
  create: createTag,
  update: updateTag,
  delete: deleteTag,
};
