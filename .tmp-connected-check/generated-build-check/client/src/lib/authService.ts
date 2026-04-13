// Authentication Service for Xano
import { xanoApi, setAuthToken, removeAuthToken } from './xanoClient';
import type { AuthResponse, User, LoginInput, SignupInput } from '@shared/schema';

/**
 * Login with email and password
 * POST https://xvaz-5ufg-teim.n7e.xano.io/api:rVbvzJH3/auth/login
 */
export async function login(credentials: LoginInput): Promise<AuthResponse> {
  const response = await xanoApi.post<{ authToken: string }>('/auth/login', credentials);
  
  // Store the auth token
  if (response.authToken) {
    setAuthToken(response.authToken);
  }
  
  // Fetch the user data using the token
  const user = await getCurrentUser();
  
  return {
    authToken: response.authToken,
    user,
  };
}

/**
 * Sign up with name, email, and password
 * POST https://xvaz-5ufg-teim.n7e.xano.io/api:rVbvzJH3/auth/signup
 */
export async function signup(userData: SignupInput): Promise<AuthResponse> {
  const response = await xanoApi.post<{ authToken: string }>('/auth/signup', userData);
  
  // Store the auth token
  if (response.authToken) {
    setAuthToken(response.authToken);
  }
  
  // Fetch the user data using the token
  const user = await getCurrentUser();
  
  return {
    authToken: response.authToken,
    user,
  };
}

/**
 * Get current authenticated user
 * GET https://xvaz-5ufg-teim.n7e.xano.io/api:rVbvzJH3/auth/me
 */
export async function getCurrentUser(): Promise<User> {
  return await xanoApi.get<User>('/auth/me');
}

/**
 * Logout - clear auth token
 */
export function logout(): void {
  removeAuthToken();
  // Dispatch logout event for app-wide state updates
  window.dispatchEvent(new CustomEvent('auth:logout'));
}

// Auth service object
export const authService = {
  login,
  signup,
  getCurrentUser,
  logout,
};

export default authService;
