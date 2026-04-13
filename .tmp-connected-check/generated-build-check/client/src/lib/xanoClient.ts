import { captureHandledError } from "../stimpact";

async function reportHandledError(input: {
  error: unknown;
  request?: { method?: string; url?: string };
  response?: { status_code?: number };
}) {
  await captureHandledError(input);
}

// Xano API Client Configuration
// This client handles all communication with the Xano backend

// Different API groups use different instance IDs
const AUTH_BASE_URL = 'https://xvaz-5ufg-teim.n7e.xano.io/api:rVbvzJH3';
const DEFAULT_BASE_URL = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';

// Helper to get the correct base URL based on endpoint
function getBaseUrl(endpoint: string): string {
  // Auth endpoints use a different API instance
  if (endpoint.startsWith('/auth')) {
    return AUTH_BASE_URL;
  }
  return DEFAULT_BASE_URL;
}

// Token management
export const AUTH_TOKEN_KEY = 'xano_auth_token';

export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function removeAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

// Enhanced fetch wrapper with auth token injection
export async function xanoRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAuthToken();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  // Merge any existing headers
  if (options.headers) {
    const existingHeaders = new Headers(options.headers);
    existingHeaders.forEach((value, key) => {
      headers[key] = value;
    });
  }

  // Add auth token if available
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = endpoint.startsWith('http') ? endpoint : `${getBaseUrl(endpoint)}${endpoint}`;
  const method = options.method ?? 'GET';

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    // Handle unauthorized responses
    if (response.status === 401) {
      removeAuthToken();
      // Optionally redirect to login or dispatch an event
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
      const error = new Error('Your session has expired. Please log in again.');
      await reportHandledError({
        error,
        request: { method, url },
        response: { status_code: response.status },
      });
      throw error;
    }

    if (!response.ok) {
      const errorText = await response.text();

      // Try to parse Xano error format: {"code":"ERROR_CODE","message":"Human readable message","payload":""}
      let errorMessage: string | null = null;
      try {
        const errorData = JSON.parse(errorText);
        if (errorData.message) {
          // Use the human-readable message from Xano
          errorMessage = errorData.message;
        }
      } catch (_parseError) {
        // If parsing fails, it's not a Xano error format
      }

      // If we have a Xano error message, use it; otherwise use status-based fallback
      if (errorMessage) {
        const error = new Error(errorMessage);
        await reportHandledError({
          error,
          request: { method, url },
          response: { status_code: response.status },
        });
        throw error;
      }

      // Fallback to generic error messages based on status code
      const statusMessages: Record<number, string> = {
        400: 'Invalid request. Please check your input and try again.',
        403: 'Access denied. Please check your credentials.',
        404: 'The requested resource was not found.',
        409: 'This action conflicts with existing data.',
        500: 'Server error. Please try again later.',
        503: 'Service temporarily unavailable. Please try again later.',
      };

      const message = statusMessages[response.status] || `An error occurred (${response.status}). Please try again.`;
      const error = new Error(message);
      await reportHandledError({
        error,
        request: { method, url },
        response: { status_code: response.status },
      });
      throw error;
    }

    // Return response data
    return await response.json();
  } catch (error) {
    await reportHandledError({
      error,
      request: { method, url },
    });
    throw error;
  }
}

// Convenience methods
export const xanoApi = {
  get: <T = any>(endpoint: string, options?: RequestInit) => 
    xanoRequest<T>(endpoint, { ...options, method: 'GET' }),
  
  post: <T = any>(endpoint: string, data?: any, options?: RequestInit) => 
    xanoRequest<T>(endpoint, {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    }),
  
  put: <T = any>(endpoint: string, data?: any, options?: RequestInit) => 
    xanoRequest<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    }),
  
  patch: <T = any>(endpoint: string, data?: any, options?: RequestInit) => 
    xanoRequest<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    }),
  
  delete: <T = any>(endpoint: string, options?: RequestInit) => 
    xanoRequest<T>(endpoint, { ...options, method: 'DELETE' }),
};

export default xanoApi;
