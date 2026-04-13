// Account Status Service for Xano
import { xanoApi, getAuthToken } from './xanoClient';
import type { AccountStatus, InsertAccountStatus, PlanTier, SubscriptionStatus } from '@shared/schema';

const BASE_PATH = '/account_status';

export interface UpdateAccountStatusInput {
  user_id?: string;
  plan_tier?: PlanTier;
  stripe_customer_id?: string;
  subscription_status?: SubscriptionStatus;
  account_status_id: string;
}

/**
 * Get all account statuses (REMOVED - security risk)
 * @deprecated DISABLED for security. Use getCurrentUserAccountStatus instead.
 */
export async function getAllAccountStatuses(): Promise<AccountStatus[]> {
  throw new Error('getAllAccountStatuses() is deprecated and disabled for security. Use getCurrent() instead.');
}

/**
 * Get current authenticated user's account status
 * This is the secure way to get account status - uses server-side proxy with requireAuth middleware
 */
export async function getCurrentUserAccountStatus(): Promise<AccountStatus | null> {
  try {
    const token = getAuthToken();
    const response = await fetch('/api/account-status/me', {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
      credentials: 'include',
    });

    if (!response.ok) {
      if (response.status === 401) {
        console.error('Unauthorized - user not authenticated');
        return null;
      }
      throw new Error(`Failed to fetch account status: ${response.statusText}`);
    }

    const accountStatus = await response.json();
    return accountStatus;
  } catch (error) {
    console.error('Failed to fetch account status:', error);
    return null;
  }
}

/**
 * Get account status by user ID (REMOVED - security risk)
 * @deprecated DISABLED for security. Use getCurrentUserAccountStatus instead.
 */
export async function getAccountStatusByUserId(userId: string): Promise<AccountStatus | null> {
  throw new Error('getAccountStatusByUserId() is deprecated and disabled for security. Use getCurrent() instead.');
}

/**
 * Get a single account status record by ID
 * GET /account_status/{account_status_id}
 */
export async function getAccountStatus(id: string): Promise<AccountStatus> {
  return xanoApi.get<AccountStatus>(`${BASE_PATH}/${id}`);
}

/**
 * Create a new account status record
 * POST /account_status
 */
export async function createAccountStatus(data: InsertAccountStatus): Promise<AccountStatus> {
  return xanoApi.post<AccountStatus>(BASE_PATH, data);
}

/**
 * Update an account status record
 * PATCH /account_status/{account_status_id}
 */
export async function updateAccountStatus(
  id: string,
  data: UpdateAccountStatusInput
): Promise<AccountStatus> {
  return xanoApi.patch<AccountStatus>(`${BASE_PATH}/${id}`, {
    ...data,
    account_status_id: id,
  });
}

/**
 * Delete an account status record
 * DELETE /account_status/{account_status_id}
 */
export async function deleteAccountStatus(id: string): Promise<void> {
  return xanoApi.delete<void>(`${BASE_PATH}/${id}`);
}

/**
 * Upgrade user's plan tier
 */
export async function upgradePlan(
  accountStatusId: string,
  newTier: PlanTier,
  stripeCustomerId?: string,
  subscriptionStatus?: SubscriptionStatus
): Promise<AccountStatus> {
  return updateAccountStatus(accountStatusId, {
    plan_tier: newTier,
    stripe_customer_id: stripeCustomerId,
    subscription_status: subscriptionStatus,
    account_status_id: accountStatusId,
  });
}

export const accountStatusService = {
  getAll: getAllAccountStatuses,
  getByUserId: getAccountStatusByUserId,
  getCurrent: getCurrentUserAccountStatus,
  getOne: getAccountStatus,
  create: createAccountStatus,
  update: updateAccountStatus,
  delete: deleteAccountStatus,
  upgradePlan,
};
