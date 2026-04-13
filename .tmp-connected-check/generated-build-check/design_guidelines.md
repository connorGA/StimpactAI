# Design Guidelines: AI Music Library Web App

## Design Approach
**Reference-Based Approach** drawing inspiration from modern music platforms (Spotify, SoundCloud, Apple Music) with a warm, inviting dark aesthetic that differentiates from the typical cold dark UIs.

**Key Design Principles:**
- Warmth in darkness: Create an inviting, cozy atmosphere using warm accent colors
- Music-first: Visual hierarchy prioritizes audio content and playability
- Gamified engagement: Make voting and requesting feel rewarding and interactive
- Premium feel: Polished, high-quality presentation matching professional streaming services

---

## Core Design Elements

### A. Color Palette

**Dark Mode Foundation:**
- Background (Primary): 15 8% 8% - Deep charcoal with warm undertone
- Background (Secondary): 20 10% 12% - Slightly lighter warm dark for cards
- Background (Elevated): 25 12% 16% - Card hover/elevated states

**Warm Accent Colors:**
- Primary Accent: 30 85% 58% - Warm amber/orange for CTAs and highlights
- Secondary Accent: 20 75% 48% - Deeper burnt orange for active states
- Success/Vote: 142 70% 45% - Muted green for vote confirmations
- Error: 0 70% 50% - Warm red for errors

**Text & Content:**
- Primary Text: 35 15% 92% - Warm off-white
- Secondary Text: 30 10% 65% - Muted warm gray
- Tertiary Text: 25 8% 45% - Subtle warm gray for metadata

**Interactive Elements:**
- Vote Button Glow: 30 90% 65% with 40% opacity
- Audio Progress: Gradient from 30 85% 58% to 20 75% 48%
- Stripe Checkout: 30 85% 58% primary button

### B. Typography

**Font Families:**
- Primary (Headings): 'Inter' or 'Manrope' - Clean, modern sans-serif
- Secondary (Body): 'Inter' - Consistent, readable
- Accent (Stats/Numbers): 'JetBrains Mono' - Monospace for vote counts and credits

**Type Scale:**
- Hero/Page Title: text-4xl to text-5xl, font-bold
- Section Headers: text-2xl to text-3xl, font-semibold
- Song Titles: text-lg, font-medium
- Body Text: text-base, font-normal
- Metadata/Labels: text-sm, font-normal
- Captions: text-xs, text-tertiary

### C. Layout System

**Spacing Primitives:** Use Tailwind units of 2, 4, 6, 8, 12, 16, 20, 24 for consistent rhythm
- Micro spacing: p-2, gap-2 (8px)
- Component padding: p-4, p-6 (16-24px)
- Section spacing: py-12, py-16, py-20 (48-80px)
- Card spacing: p-6, p-8 (24-32px)

**Grid Systems:**
- Music Library: grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6
- Leaderboard: Single column with cards, max-w-4xl centered
- Container: max-w-7xl mx-auto px-6

### D. Component Library

**Navigation:**
- Fixed header with blur backdrop (backdrop-blur-xl bg-background/80)
- Logo/brand on left with warm accent glow
- Vote credit balance prominently displayed (pill with accent background)
- "Buy Credits" CTA button in warm accent color
- Admin indicator for logged-in admin (subtle badge)

**Music Library Cards:**
- Aspect ratio 1:1 thumbnail with subtle rounded corners (rounded-xl)
- Hover state: scale-105 transform with warm glow shadow
- Overlay gradient on hover revealing play button
- Song title (truncate with ellipsis), artist name below
- Audio waveform visualization on active play (optional visual enhancement)
- Duration badge in bottom-right corner

**Audio Player:**
- Persistent bottom player bar when song is active
- Album art (square, 64px), song info, play/pause, progress bar
- Volume control, timestamp display
- Warm accent color for progress bar with glow effect
- Smooth transitions between tracks

**Song Request Form:**
- Centered modal/card design with backdrop blur
- Input fields with warm accent focus rings
- Character count for request field
- Submit button with warm accent, disabled state when empty
- Success animation when request submitted (confetti or glow pulse)

**Leaderboard:**
- Card-based layout with rank badges (1st/2nd/3rd special styling)
- Large vote count in monospace font with warm accent
- Request text prominently displayed
- Vote button on right (outline style when no credits, solid when credits available)
- Smooth reordering animation when votes change
- Progress bar showing relative vote percentage vs top request

**Vote Credit Purchase:**
- Pricing cards in 2-3 column grid
- Highlight "Best Value" option with warm accent border and glow
- Credit packages: 5 credits, 20 credits (+bonus), 50 credits (+bonus)
- Stripe checkout button with lock icon for security
- Clean, trustworthy design with subtle payment badges

**Admin Interface:**
- Toggle switch to enter/exit admin mode (top navigation)
- Upload card with drag-drop zone (dashed border with warm accent)
- Form fields for title, artist, thumbnail URL, audio URL
- Preview before publish
- Edit/Delete buttons on library cards when in admin mode (destructive action confirmation)

### E. Interactions & Animations

**Minimal, Purposeful Animations:**
- Card hover: transform scale-105, duration-200, ease-out
- Vote button click: Scale pulse + glow flash (200ms)
- Audio loading: Subtle spinner in warm accent
- Leaderboard reorder: smooth y-axis translation (300ms)
- Success states: Gentle fade-in with scale (200ms)
- Page transitions: Fade between views (150ms)

**Audio Interactions:**
- Play button: Morphs to pause with rotation
- Waveform: Subtle pulse on beat (if feasible)
- Progress bar: Smooth drag interaction with warm glow trail

---

## Images

**No large hero image required** - this is a utility app focused on the music library grid.

**Thumbnail Images:**
- Song thumbnails: 1:1 aspect ratio, album art style
- AI-generated abstract art or music-themed visuals
- Consistent rounded corners (rounded-xl)
- High quality, min 400x400px for clarity

**Empty States:**
- Illustrated empty library state (warm-toned illustration)
- No requests illustration for empty leaderboard
- Zero credits state with friendly prompt to purchase

---

## Page-Specific Layouts

**Main Library View:**
- Header with navigation + vote credits display
- Optional filter/search bar below header
- Music grid (responsive columns)
- Floating "Request Song" button (bottom-right, warm accent glow)

**Leaderboard View:**
- Header with "Song Requests" title
- Top 3 requests with medal badges and enhanced styling
- Scrollable list below with rank numbers
- Sticky "Submit Request" CTA at top

**Credits Purchase:**
- Centered pricing cards with clear value proposition
- Trust indicators (secure checkout, satisfaction guarantee)
- Stripe-powered checkout flow with brand consistency

**Admin Upload:**
- Split layout: form on left, preview on right
- Clear field labels, validation feedback
- Publish button prominent with confirmation state

---

## Accessibility & Responsive Design

- All interactive elements min 44x44px touch targets
- Warm accent meets WCAG AA contrast on dark backgrounds
- Audio controls keyboard accessible (space to play/pause, arrow keys for seeking)
- Mobile: Stack to single column, maintain card aspect ratios
- Touch-friendly vote buttons on mobile (larger tap area)
- Persistent audio player adapts to mobile bottom navigation area