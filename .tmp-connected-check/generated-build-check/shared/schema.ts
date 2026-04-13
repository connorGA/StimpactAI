import { z } from "zod";

// ==================== XANO TYPES ====================
// These types match the Xano database schema

// User
export interface User {
  id: string;
  created_at: number;
  name: string;
  email: string;
  username: string;
  avatar_url?: string;
  bio?: string;
  role: string;
  updated_at: number;
}

export const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

export const signupSchema = z.object({
  name: z.string().min(1),
  email: z.string().email(),
  password: z.string().min(6),
});

export type LoginInput = z.infer<typeof loginSchema>;
export type SignupInput = z.infer<typeof signupSchema>;

// Auth Response
export interface AuthResponse {
  authToken: string;
  user: User;
}

// Track
export interface Track {
  id: string;
  created_at: number;
  title: string;
  artist: string;
  genre: string;
  display_artist: string;
  duration_seconds: number;
  bpm?: number;
  musical_key?: string;
  loudness_lufs?: number;
  cover_image_url?: string;
  cover_position?: string; // CSS object-position value, e.g., "center top", "50% 25%"
  audio_url: string;
  preview_url?: string;
  waveform_json_url?: string;
  release_date?: string;
  provider?: string;
  prompt_text?: string;
  seed?: number;
  rights_status?: string;
  updated_at: number;
  is_deleted: boolean;
  streams: number;
  last_streamed_at?: number;
}

// Playlist
export interface Playlist {
  id: string;
  created_at: number;
  name: string;
  description?: string;
  cover_image_url?: string;
  privacy: string; // e.g., 'public', 'private'
  updated_at: number;
  is_deleted: boolean;
  user_id: string;
}

// Playlist Track
export interface PlaylistTrack {
  id: string;
  created_at: number;
  sort_index: number;
  added_at: number;
  playlist_id: string;
  track_id: string;
}

// Saved Track
export interface SavedTrack {
  id: string;
  created_at: number;
  user_id: string;
  track_id: string;
}

// Playback Event
export interface PlaybackEvent {
  id: string;
  created_at: number;
  played_ms: number;
  user_id: string;
  track_id: string;
}

// Moderation Event
export interface ModerationEvent {
  id: string;
  created_at: number;
  reason: string;
  track_id: string;
}

// Tag
export interface Tag {
  id: string;
  created_at: number;
  type: string;
  name: string;
}

// Track Tag
export interface TrackTag {
  id: string;
  created_at: number;
  track_id: string;
  tag_id: string;
}

// Session
export interface Session {
  id: string;
  created_at: number;
  token_hash: string;
  expires_at: number;
  user_id: string;
}

// Request
export interface Request {
  id: string;
  created_at: number;
  title: string;
  artist: string;
  genre: string;
  description: string;
  votes: number;
  released: boolean;
  release_date?: number;
}

// Credits
export interface Credits {
  id: string;
  created_at: number;
  user_id: string;
  credits: number;
  last_spend?: number;
  last_refilled?: number;
}

// Account Status
export type PlanTier = 'free' | 'plus' | 'premium' | 'platinum' | 'admin';
export type SubscriptionStatus = 'active' | 'canceled' | 'past_due' | 'none';

export interface AccountStatus {
  id: string;
  created_at: number;
  user_id: string;
  plan_tier: PlanTier;
  stripe_customer_id?: string;
  subscription_status?: SubscriptionStatus;
  credits_id?: string | null;
}

// Plan limits and features
export const PLAN_LIMITS = {
  free: {
    maxSavedTracks: 0,
    maxPlaylists: 0,
    monthlyCredits: 0,
    canRequestSongs: false,
    canUpvote: false,
  },
  plus: {
    maxSavedTracks: Infinity,
    maxPlaylists: 3,
    monthlyCredits: 200,
    canRequestSongs: true,
    canUpvote: true,
  },
  premium: {
    maxSavedTracks: Infinity,
    maxPlaylists: Infinity,
    monthlyCredits: 1000,
    canRequestSongs: true,
    canUpvote: true,
  },
  platinum: {
    maxSavedTracks: Infinity,
    maxPlaylists: Infinity,
    monthlyCredits: 3000,
    canRequestSongs: true,
    canUpvote: true,
  },
  admin: {
    maxSavedTracks: Infinity,
    maxPlaylists: Infinity,
    monthlyCredits: Infinity,
    canRequestSongs: true,
    canUpvote: true,
  },
} as const;

// ==================== INSERT SCHEMAS ====================
// Zod schemas for creating new records

export const insertTrackSchema = z.object({
  title: z.string().min(1),
  artist: z.string().min(1),
  genre: z.string().min(1),
  display_artist: z.string().min(1).optional(),
  duration_seconds: z.number().int().positive(),
  bpm: z.number().int().optional(),
  musical_key: z.string().optional(),
  loudness_lufs: z.number().optional(),
  cover_image_url: z.string().url().optional(),
  cover_position: z.string().optional(), // CSS object-position value, e.g., "center top", "50% 25%"
  audio_url: z.string().url(),
  preview_url: z.string().url().optional(),
  waveform_json_url: z.string().url().optional(),
  release_date: z.string().optional(),
  provider: z.string().optional(),
  prompt_text: z.string().optional(),
  seed: z.number().int().optional(),
  rights_status: z.string().optional(),
  updated_at: z.number().int(),
  is_deleted: z.boolean(),
  streams: z.number().int().nonnegative().default(0),
  last_streamed_at: z.number().int().optional(),
});

export const insertPlaylistSchema = z.object({
  name: z.string().min(1),
  description: z.string().optional(),
  cover_image_url: z.string().url().optional(),
  privacy: z.enum(['public', 'private']).default('public'),
  user_id: z.string().uuid(),
});

export const insertPlaylistTrackSchema = z.object({
  sort_index: z.number(),
  playlist_id: z.string().uuid(),
  track_id: z.string().uuid(),
});

export const insertSavedTrackSchema = z.object({
  user_id: z.string().uuid(),
  track_id: z.string().uuid(),
});

export const insertPlaybackEventSchema = z.object({
  played_ms: z.number().int().nonnegative(),
  user_id: z.string().uuid(),
  track_id: z.string().uuid(),
});

export const insertModerationEventSchema = z.object({
  reason: z.string().min(1),
  track_id: z.string().uuid(),
});

export const insertTagSchema = z.object({
  type: z.string().min(1),
  name: z.string().min(1),
});

export const insertTrackTagSchema = z.object({
  track_id: z.string().uuid(),
  tag_id: z.string().uuid(),
});

export const insertRequestSchema = z.object({
  title: z.string().min(1),
  artist: z.string().min(1),
  genre: z.string().min(1),
  description: z.string().optional(),
  votes: z.number().int().nonnegative().default(0),
  released: z.boolean().default(false),
  release_date: z.number().int().optional(),
});

export const insertCreditsSchema = z.object({
  user_id: z.string().uuid(),
  credits: z.number().int().nonnegative(),
  last_spend: z.number().int().optional(),
  last_refilled: z.number().int().optional(),
});

export const insertAccountStatusSchema = z.object({
  user_id: z.string().uuid(),
  plan_tier: z.enum(['free', 'plus', 'premium', 'platinum', 'admin']),
  stripe_customer_id: z.string().optional(),
  subscription_status: z.enum(['active', 'canceled', 'past_due', 'none']).optional(),
});

// ==================== CREDIT PACKAGES ====================

export interface CreditPackage {
  id: string;
  name: string;
  credits: number;
  price: number; // in dollars
  popular?: boolean;
  stripePaymentLink?: string;
}

export const CREDIT_PACKAGES: CreditPackage[] = [
  {
    id: 'starter',
    name: 'Starter Pack',
    credits: 200,
    price: 4.99,
  },
  {
    id: 'power',
    name: 'Power Pack',
    credits: 1000,
    price: 9.99,
    popular: true,
  },
  {
    id: 'ultimate',
    name: 'Ultimate Pack',
    credits: 3000,
    price: 19.99,
  },
] as const;

export interface SubscriptionPlan {
  id: string;
  tier: PlanTier;
  name: string;
  price: number;
  monthlyCredits: number;
  features: string[];
  recommended?: boolean;
  stripePaymentLink?: string;
}

export const SUBSCRIPTION_PLANS: SubscriptionPlan[] = [
  {
    id: 'plus',
    tier: 'plus',
    name: 'Plus',
    price: 4.99,
    monthlyCredits: 200,
    features: [
      'Unlimited saved tracks',
      'Up to 3 playlists',
      '200 credits per month',
      'Request songs',
      'Upvote requests',
    ],
  },
  {
    id: 'premium',
    tier: 'premium',
    name: 'Premium',
    price: 9.99,
    monthlyCredits: 1000,
    features: [
      'Unlimited saved tracks',
      'Unlimited playlists',
      '1,000 credits per month',
      'Request songs',
      'Upvote requests',
      'Priority support',
    ],
    recommended: true,
  },
  {
    id: 'platinum',
    tier: 'platinum',
    name: 'Platinum',
    price: 19.99,
    monthlyCredits: 3000,
    features: [
      'Unlimited saved tracks',
      'Unlimited playlists',
      '3,000 credits per month',
      'Request songs',
      'Upvote requests',
      'Priority support',
      'Early access to new features',
    ],
  },
] as const;

// ==================== TYPE EXPORTS ====================

export type InsertTrack = z.infer<typeof insertTrackSchema>;
export type InsertPlaylist = z.infer<typeof insertPlaylistSchema>;
export type InsertPlaylistTrack = z.infer<typeof insertPlaylistTrackSchema>;
export type InsertSavedTrack = z.infer<typeof insertSavedTrackSchema>;
export type InsertPlaybackEvent = z.infer<typeof insertPlaybackEventSchema>;
export type InsertModerationEvent = z.infer<typeof insertModerationEventSchema>;
export type InsertTag = z.infer<typeof insertTagSchema>;
export type InsertTrackTag = z.infer<typeof insertTrackTagSchema>;
export type InsertRequest = z.infer<typeof insertRequestSchema>;
export type InsertCredits = z.infer<typeof insertCreditsSchema>;
export type InsertAccountStatus = z.infer<typeof insertAccountStatusSchema>;