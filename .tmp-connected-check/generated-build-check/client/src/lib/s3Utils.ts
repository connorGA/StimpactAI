/**
 * S3 utilities for handling signed URLs
 */

interface SignedUrlResponse {
  signedUrl: string;
}

/**
 * Cache for signed URLs to avoid regenerating them frequently
 * Maps S3 URL -> { signedUrl: string, expiresAt: number }
 */
const signedUrlCache = new Map<string, { signedUrl: string; expiresAt: number }>();

/**
 * Get a signed URL for an S3 object
 * @param s3Url - The S3 URL to sign
 * @param expiresIn - How long the URL should be valid (default: 1 hour)
 * @returns A signed URL that can be used to access the S3 object
 */
export async function getSignedUrl(s3Url: string, expiresIn: number = 3600): Promise<string> {
  // Validate input is a non-empty string
  if (!s3Url || typeof s3Url !== 'string' || s3Url.trim() === '') {
    return '';
  }

  // If it's not an S3 URL, return as-is
  if (!s3Url.includes('.s3.') && !s3Url.includes('s3.amazonaws.com')) {
    return s3Url;
  }

  // Check cache first (with 5 minute buffer before expiry)
  const cached = signedUrlCache.get(s3Url);
  const now = Date.now();
  if (cached && cached.expiresAt > now + 5 * 60 * 1000) {
    return cached.signedUrl;
  }

  try {
    // Get auth token for the request
    const token = localStorage.getItem('xano_auth_token');
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    // Include auth token if available (optional)
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch('/api/s3/signed-url', {
      method: 'POST',
      headers,
      body: JSON.stringify({ url: s3Url, expiresIn }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Failed to get signed URL:', errorText);
      // Return empty string instead of raw S3 URL to avoid 403 errors
      return '';
    }

    const data: SignedUrlResponse = await response.json();

    // Cache the signed URL
    signedUrlCache.set(s3Url, {
      signedUrl: data.signedUrl,
      expiresAt: now + (expiresIn * 1000),
    });

    return data.signedUrl;
  } catch (error) {
    console.error('Error getting signed URL:', error);
    // Return empty string instead of raw S3 URL to avoid 403 errors
    return '';
  }
}

/**
 * Batch get signed URLs for multiple S3 URLs
 * @param s3Urls - Array of S3 URLs to sign
 * @param expiresIn - How long the URLs should be valid (default: 1 hour)
 * @returns Array of signed URLs in the same order as input
 */
export async function getSignedUrls(s3Urls: string[], expiresIn: number = 3600): Promise<string[]> {
  return Promise.all(s3Urls.map(url => getSignedUrl(url, expiresIn)));
}

/**
 * Clear the signed URL cache
 */
export function clearSignedUrlCache(): void {
  signedUrlCache.clear();
}

// Function to handle play errors
export function handlePlayError(error: Error): void {
  if (error.message.includes('The play() request was interrupted by a call to pause()')) {
    console.warn('Play request was interrupted by pause() - this is expected during rapid play/pause.');
    // No further action needed, the UI should handle this state.
  } else {
    // Log other unexpected errors
    console.error('Playback error:', error);
  }
}