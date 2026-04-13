# AI Music Library Web Application

## Overview
An AI-generated music library platform enabling users to browse, play, and request AI-generated songs. It features a voting system for song requests, credit-based purchasing via Stripe, and administrative controls for managing the music catalog. The platform aims to offer a unique listening experience with AI-generated content, supported by a modern tech stack.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
**Core Framework**: React 18 with TypeScript.
**Routing**: Wouter for lightweight client-side routing.
**State Management**: React Context API for music player state; TanStack Query for server state.
**UI Framework**: Shadcn UI components built on Radix UI primitives.
**Styling**: Tailwind CSS with a custom design system featuring warm dark mode aesthetics.
**Key Design Decisions**: Component-based architecture, global music player context, custom design system with warm accent colors, and responsive design with a mobile-first approach.

### Backend Architecture
**Server Framework**: Express.js with TypeScript and ES Modules.
**Development**: Vite middleware for HMR.
**Storage Interface**: Abstract storage layer (currently MemStorage) designed for future database integration.
**Key Design Decisions**: Abstract storage interface for easy migration, separation of concerns with modular route registration, and environment-specific configurations.

### Data Architecture
**Backend**: Xano No-Code Platform, utilizing two separate APIs for authentication and data.
**Schema Location**: TypeScript interfaces in `/shared/schema.ts`.
**Auth Method**: JWT tokens stored in localStorage.
**Implemented API Services**: Comprehensive services for authentication, account status, credits, moderation, playback, playlists, saved tracks, sessions, tags, and tracks.
**Current Schema**: Includes User, AccountStatus (subscription tiers), Credits, Track, Playlist, PlaylistTrack, SavedTrack, PlaybackEvent, ModerationEvent, Tag/TrackTag, and Session.
**Key Design Decisions**: Shared TypeScript interfaces for type safety, Zod schemas for validation, UUID primary keys, automatic auth token injection, and 401 response handling for logout flows.

### Data Privacy & Security
**Critical Security Implementation**: All user-scoped data fetching now uses secure server-side proxy endpoints with requireAuth middleware and server-side filtering. Direct Xano API calls that could expose other users' data are completely disabled.

**Secure Endpoints**:
- `GET /api/account-status/me` - Returns only current user's account status (including plan_tier) with server-side filtering
- `GET /api/playlists` - Returns only current user's playlists (filtered by req.user.id)
- `GET /api/saved-tracks` - Returns only current user's saved tracks (filtered by req.user.id)
- `GET /api/credits/me` - Returns only current user's credits with ownership verification
- All playlist CRUD operations use server proxies with ownership verification

**Disabled Unsafe Methods** (throw errors if called):
- `playlistService.getAll()` - Would return all users' playlists
- `playlistService.getByUserId()` - Could query any user's playlists
- `savedTrackService.getAll()` - Would return all users' saved tracks
- `savedTrackService.getByUserId()` - Could query any user's saved tracks
- `accountStatusService.getAll()` - Would return all users' account statuses
- `accountStatusService.getByUserId()` - Could query any user's account status

**Security Pattern**: All user data queries follow this pattern:
1. Frontend calls service.getCurrent() method
2. getCurrent() makes authenticated request to /api/{resource} server endpoint
3. Server endpoint extracts user_id from JWT token (req.user.id)
4. Server fetches from Xano with user_id query parameter
5. Server applies additional filtering to ensure only matching user_id records are returned
6. No-cache headers prevent stale data exposure

**Account Status Management**: Account status records are only created during user signup. No auto-creation on login or page refresh to prevent duplicate records.

### UI/UX Design System
**Typography**: Inter for primary text, JetBrains Mono for statistics.
**Color System**: Warm dark mode foundation with amber/orange primary accents and semantic colors.
**Component Patterns**: Card-based layouts, consistent border radius, shadow system for depth, and gamified interactions.
**Mobile Responsive Design**: Comprehensive mobile styling implemented at 768px breakpoint with highly compact layouts. Music and playlist cards use 2-column grid on mobile (grid-cols-2) with significantly reduced padding (p-1), smaller text (text-xs for titles, text-[10px] for secondary), and tighter spacing (gap-2). Request cards (LeaderboardCard) ultra-compact on mobile: p-3 padding, hidden descriptions, h-1.5 (6px) progress bars, space-y-1 section spacing, text-[11px] minimum for accessibility, line-clamp-1 titles, and h-9 w-9 (36px) vote buttons. Info banners compressed on mobile with reduced padding, smaller icons, and shortened text. All interactive elements maintain 36-40px minimum touch targets for accessibility. Mobile navigation includes Requests page in profile dropdown menu. Design goal: 3+ request cards visible in 375x667 viewport without scrolling. Navbar uses consistent container margins (container mx-auto px-2 sm:px-6) matching page content. Mobile playbar enhanced with dedicated timeline row showing current time, seek slider, duration, and skip controls (32px disabled buttons) above song info, providing full playback controls on mobile while maintaining horizontal three-section desktop layout. Song request form (RequestSongDialog) fully responsive: dialog width max-w-[95vw] on mobile vs max-w-5xl on desktop, credit banner stacks vertically (flex-col) on mobile, form sections use gap-4 on mobile vs gap-8 on desktop, all text scales down (text-xs/sm on mobile vs text-base/lg on desktop), action buttons full-width on mobile (w-full) with shorter submit text. GenreWheel component compact on mobile: gap-1.5 vs gap-2, genre buttons text-xs vs text-sm, sub-genre spacing reduced (space-y-0.5 vs space-y-1, pl-2 vs pl-4), instructions text-[11px] vs text-xs, popular styles badges text-xs vs text-sm. Pricing menus (PurchaseCreditsDialog) optimized for mobile: dialog padding p-3 on mobile vs p-6 on desktop, grid-cols-2 sm:grid-cols-3 layout (2 columns <640px, 3 columns ≥640px), gap-2 sm:gap-4 spacing. SubscriptionPlanCard uses text-[11px] minimum (WCAG AA compliant), price text-xl sm:text-4xl, all 5 features visible with natural text wrapping (no line-clamp), full button labels ("Subscribe", "Current Plan", "Continue Free"). CreditPackageCard uses text-xs for package names, text-xl for prices, text-[11px] for labels, all pricing information visible including value-per-credit metric. Cards fit side-by-side on mobile (~135-165px per card) with proper wrapping to next row, maintaining accessibility and complete information visibility.

### Feature Specifications
**Admin Features**: Admin plan tier with complete access control implemented via server-side authentication middleware (requireAuth verifies JWT with Xano, requireAdmin validates plan_tier). Dedicated Create page (/create) for publishing tracks with file uploads (audio, cover art) stored in object storage. Protected upload endpoints (POST /api/upload/audio, POST /api/upload/cover) return 401 for unauthenticated requests and 403 for non-admin users. Frontend route protection with loading state checks prevents premature redirects.

**Monetization**: Hybrid subscription model (Free, Plus, Premium, Platinum, Admin) with feature gating via `usePlanLimits` hook. Credit-based system for song requests and voting. One-time credit purchase packages available via Stripe:
- Starter Pack: 100 credits for $4.99
- Power Pack: 500 credits for $19.99
- Ultimate Pack: 1500 credits for $49.99

**User Library & Playlists**: User-scoped Library page for saved tracks, comprehensive playlist management (create, add, remove tracks), and a dedicated "Playlists" navigation tab. Playlist cover customization with custom image uploads (small round "+" button at top-right of cover) or auto-generated mosaics from track thumbnails (1 track: full image, 2 tracks: split view, 3 tracks: asymmetric grid, 4+ tracks: 2x2 grid of first 4 tracks). Default Synthetic Soul neon sign image used when no custom cover or track art exists. Cover uploads stored in S3 with playlist-covers/ prefix, accessible via signed URLs. Playlist playback controls include large play button and shuffle toggle next to title; play button starts sequential or shuffled playback based on shuffle state. Queue management auto-advances to next track when current song ends.

**Enhanced Genre Selection**: Redesigned Request Song dialog with an interactive GenreWheel component for selecting main and sub-genres.

**Credit System**: Separate Credits table, real-time credit display, Requests page with voting and request creation functionality, including duplicate detection and client-side rollback for credit refunds. Clickable credit badge in header opens PurchaseCreditsDialog for purchasing credits or subscribing to plans. Insufficient credit flows automatically open purchase dialog.

**Payment Integration**: Secure Stripe payment flow for subscriptions and one-time credit purchases. Server validates package selection against trusted CREDIT_PACKAGES constant to prevent price tampering. Payment endpoint (POST /api/create-payment-intent) requires authentication and validates packageId server-side. 

**Webhook Processing**: Robust idempotency and event handling implemented to prevent duplicate credit additions:
- **checkout.session.completed**: Handles new subscriptions (adds plan tier + initial monthly credits from PLAN_LIMITS) and one-time credit purchases (adds purchased credits from metadata.creditAmount). Session IDs tracked in-memory with success flag pattern to prevent duplicate processing on Stripe retries. For subscriptions, only monthly credits are added (not creditAmount).
- **invoice.paid**: Handles subscription renewals ONLY with billing_reason filter. Skips initial subscription invoices (billing_reason='subscription_create') since already processed by checkout.session.completed. Only processes recurring invoices (billing_reason='subscription_cycle') to add monthly credits.
- **Single Credit Writer**: Webhook is the ONLY place that creates initial credit records. Frontend App.tsx only fetches existing credits (no auto-creation). Free users without purchases show 0 credits via synthetic API response.
- **Atomic Credit Operations**: Thread-safe credit additions with per-user locking mechanism prevents race conditions. Credits are added to existing user credit record or new record is created and linked to account_status.
- **Error Recovery**: Failed webhook processing removes session from processed set, allowing legitimate retries while preventing duplicate credit grants on success.

## External Dependencies

### Payment Processing
- **Stripe**: Payment gateway for credit purchases and subscription management.
- **@stripe/stripe-js** and **@stripe/react-stripe-js**: For frontend Stripe integration.

### Database & Storage
- **Neon Serverless PostgreSQL**: Primary database.
- **Drizzle ORM**: Type-safe database queries.
- **AWS S3**: Private object storage for audio files, cover images, and playlist covers. Files are uploaded with unique timestamps and random hashes to prevent collisions. S3 bucket configured with Block Public Access enabled for security. Access is controlled via pre-signed URLs with 1-hour expiration (cached client-side for 55 minutes). Signed URL endpoint (POST /api/s3/signed-url) requires authentication and validates keys must start with audio/, covers/, or playlist-covers/ prefixes. Track upload endpoints require admin authentication; playlist cover uploads require user authentication only. Frontend uses useSignedTracks hook with stable dependencies to prevent render loops.

### UI Component Libraries
- **Radix UI**: Accessible component primitives.
- **Shadcn UI**: Pre-built UI components.
- **cmdk**: Command palette.
- **vaul**: Drawer component library.

### Development Tools
- **Vite**: Build tool and dev server.
- **TypeScript**: For type safety.
- **TanStack Query**: Data fetching and caching.
- **React Hook Form**: Form management with Zod validation.
- **Wouter**: Lightweight routing.

### Utilities
- **date-fns**: Date manipulation.
- **clsx**, **tailwind-merge**: For dynamic class name composition.
- **nanoid**: Unique ID generation.
- **class-variance-authority**: Component variant management.