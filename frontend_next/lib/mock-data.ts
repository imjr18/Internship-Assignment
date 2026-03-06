import type { Restaurant, AppState, BookingFields } from './types'

export const RESTAURANTS: Restaurant[] = [
  {
    id: 'rest-001',
    name: 'Amber Kitchen',
    neighborhood: 'Uptown',
    cuisine_type: 'Japanese',
    price_range: 3,
    total_capacity: 43,
    dietary_certifications: ['nut_allergy_safe', 'gluten_free_options'],
    ambiance_tags: ['business_lunch', 'outdoor_seating', 'romantic', 'quiet'],
    operating_hours: { open: '17:00', close: '23:30' },
    description:
      'Bringing the best of Japanese cuisine to Uptown with a vibrant, charming setting.',
  },
  {
    id: 'rest-002',
    name: 'Sol Nest',
    neighborhood: 'Harbor District',
    cuisine_type: 'Chinese',
    price_range: 4,
    total_capacity: 38,
    dietary_certifications: ['vegan_friendly'],
    ambiance_tags: ['quiet', 'romantic', 'waterfront'],
    operating_hours: { open: '18:00', close: '23:00' },
    description:
      'Elegant Chinese cuisine with stunning harbor views and a serene atmosphere.',
  },
  {
    id: 'rest-003',
    name: 'The Olive Press',
    neighborhood: 'West End',
    cuisine_type: 'Mediterranean',
    price_range: 2,
    total_capacity: 55,
    dietary_certifications: ['vegan_friendly', 'gluten_free_options'],
    ambiance_tags: ['family_friendly', 'outdoor_seating', 'lively'],
    operating_hours: { open: '11:00', close: '22:00' },
    description: 'Fresh Mediterranean flavors in a warm, welcoming setting.',
  },
  {
    id: 'rest-004',
    name: 'Maison Blanc',
    neighborhood: 'Downtown',
    cuisine_type: 'French',
    price_range: 4,
    total_capacity: 28,
    dietary_certifications: [],
    ambiance_tags: ['romantic', 'quiet', 'business_lunch', 'historic'],
    operating_hours: { open: '17:00', close: '23:00' },
    description:
      'Classic French fine dining in an intimate historic Downtown setting.',
  },
  {
    id: 'rest-005',
    name: 'Spice Route',
    neighborhood: 'Midtown',
    cuisine_type: 'Indian',
    price_range: 2,
    total_capacity: 60,
    dietary_certifications: ['vegan_friendly', 'halal_certified'],
    ambiance_tags: ['family_friendly', 'lively', 'casual'],
    operating_hours: { open: '12:00', close: '22:30' },
    description:
      'Vibrant Indian cuisine with generous portions and a festive atmosphere.',
  },
  {
    id: 'rest-006',
    name: 'Ember & Rye',
    neighborhood: 'East Village',
    cuisine_type: 'American',
    price_range: 3,
    total_capacity: 72,
    dietary_certifications: ['gluten_free_options'],
    ambiance_tags: ['lively', 'casual', 'outdoor_seating'],
    operating_hours: { open: '11:00', close: '01:00' },
    description:
      'Bold American grill with craft beers and a buzzing East Village energy.',
  },
]

/* ── Cuisine display helpers ── */

export const CUISINE_EMOJIS: Record<string, string> = {
  Japanese:      '🍜',
  Chinese:       '🥟',
  Mediterranean: '🫒',
  French:        '🥐',
  Indian:        '🫕',
  American:      '🍔',
  Italian:       '🍝',
  Thai:          '🍛',
  Korean:        '🍱',
}

export const CUISINE_GRADIENTS: Record<string, string> = {
  Japanese:      'linear-gradient(160deg, #1a1400, #0d0d0d)',
  Chinese:       'linear-gradient(160deg, #1a0d0d, #0d0d0d)',
  Mediterranean: 'linear-gradient(160deg, #0d150d, #0d0d0d)',
  French:        'linear-gradient(160deg, #0d0d1a, #0d0d0d)',
  Indian:        'linear-gradient(160deg, #1a0f00, #0d0d0d)',
  American:      'linear-gradient(160deg, #1a0d00, #0d0d0d)',
  default:       'linear-gradient(160deg, #1a1400, #0d0d0d)',
}

export function getCuisineEmoji(cuisine: string) {
  return CUISINE_EMOJIS[cuisine] ?? '🍽️'
}

export function getCuisineGradient(cuisine: string) {
  return CUISINE_GRADIENTS[cuisine] ?? CUISINE_GRADIENTS.default
}

/* ── Price ── */

export function priceSymbols(n: number) {
  return '$'.repeat(Math.max(1, Math.min(4, n)))
}

// Backward-compatible alias used by older components.
export const PRICE_SYMBOLS = priceSymbols

/* ── Dietary ── */

export const DIETARY_LABELS: Record<string, { label: string; color: string }> = {
  nut_allergy_safe:     { label: 'Nut-Free Kitchen',    color: '#3d9e6a' },
  gluten_free_options:  { label: 'Gluten-Free Options', color: '#3d9e6a' },
  vegan_friendly:       { label: 'Vegan Friendly',      color: '#3d9e6a' },
  halal_certified:      { label: 'Halal Certified',     color: '#5b9ebf' },
  kosher_certified:     { label: 'Kosher Certified',    color: '#5b9ebf' },
}

/* ── Tag display ── */

export function tagLabel(tag: string) {
  const map: Record<string, string> = {
    business_lunch:  'Business Lunch',
    outdoor_seating: 'Outdoor Seating',
    romantic:        'Romantic',
    quiet:           'Quiet',
    waterfront:      'Waterfront',
    family_friendly: 'Family Friendly',
    lively:          'Lively',
    casual:          'Casual',
    historic:        'Historic',
  }
  return map[tag] ?? tag.replace(/_/g, ' ')
}

/* ── Initial state ── */

export const INITIAL_BOOKING_FIELDS: BookingFields = {
  restaurant: null,
  partySize: null,
  date: null,
  time: null,
  occasion: null,
}

const uid = () => Math.random().toString(36).slice(2)

/* ── Demo state snapshots ── */

export function buildState(uiState: 1 | 2 | 3 | 4): Partial<AppState> {
  switch (uiState) {
    /* ─ State 1: Landing ─ */
    case 1:
      return {
        screen: 'book',
        bookingState: 'GREETING',
        messages: [],
        bookingFields: { ...INITIAL_BOOKING_FIELDS },
        searchResults: [],
        confirmationCode: null,
      }

    /* ─ State 2: Mid-conversation, Sage composing ─ */
    case 2:
      return {
        screen: 'book',
        bookingState: 'PRESENTING_OPTIONS',
        messages: [
          {
            id: uid(),
            role: 'user',
            content:
              "I'm looking for a romantic dinner for 2 this Saturday evening, somewhere quiet in Uptown or Downtown.",
          },
          {
            id: uid(),
            role: 'sage',
            content:
              "I have just the place for you. Amber Kitchen in Uptown is a beautiful Japanese restaurant known for its quiet, romantic setting and exceptional cuisine. They have availability this Saturday evening and their gluten-free kitchen makes it suitable for a wide range of guests. Would you like me to check the exact availability for Saturday?",
          },
          {
            id: uid(),
            role: 'user',
            content: 'Yes please, around 8pm would be perfect.',
          },
          {
            id: uid(),
            role: 'composing',
            content: '',
          },
        ],
        bookingFields: {
          restaurant: 'Amber Kitchen',
          partySize: '2',
          date: 'Saturday',
          time: 'Evening',
          occasion: null,
        },
        searchResults: [RESTAURANTS[0], RESTAURANTS[3], RESTAURANTS[1]],
        confirmationCode: null,
      }

    /* ─ State 3: Confirmed ─ */
    case 3:
      return {
        screen: 'book',
        bookingState: 'COMPLETED',
        messages: [
          {
            id: uid(),
            role: 'user',
            content:
              "I'm looking for a romantic dinner for 2 this Saturday evening, somewhere quiet.",
          },
          {
            id: uid(),
            role: 'sage',
            content:
              "Wonderful. I have a table available for 2 at Amber Kitchen this Saturday at 8:00 PM. To complete your reservation, could you share your name and email address?",
          },
          {
            id: uid(),
            role: 'user',
            content: 'Jamie Chen, jamie@email.com',
          },
          {
            id: uid(),
            role: 'sage',
            content:
              "Your reservation is confirmed, Jamie. I've secured a quiet table for 2 at Amber Kitchen this Saturday at 8:00 PM. You'll receive a confirmation email shortly.",
          },
        ],
        bookingFields: {
          restaurant: 'Amber Kitchen',
          partySize: '2',
          date: 'Saturday, Mar 8',
          time: '8:00 PM',
          occasion: null,
        },
        searchResults: [RESTAURANTS[0]],
        confirmationCode: 'GF-8821-KXTP',
      }

    /* ─ State 4: Browse page ─ */
    case 4:
      return {
        screen: 'browse',
        bookingState: 'GREETING',
        messages: [],
        bookingFields: { ...INITIAL_BOOKING_FIELDS },
        searchResults: [],
        confirmationCode: null,
      }

    default:
      return {}
  }
}
