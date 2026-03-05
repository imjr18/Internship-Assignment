'use client'

import { RESTAURANTS, getCuisineEmoji, getCuisineGradient, priceSymbols, tagLabel, DIETARY_LABELS } from '@/lib/mock-data'
import type { AppState, Restaurant } from '@/lib/types'

/* ─── shared micro-heading ─── */
function MicroHeading({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="uppercase"
      style={{ fontSize: '10px', letterSpacing: '0.15em', color: '#504a44', marginBottom: '20px' }}
    >
      {children}
    </p>
  )
}

function Divider() {
  return <div style={{ height: '1px', background: '#1a1a1a', margin: '24px 0' }} />
}

/* ─── Ambiance pill ─── */
function Tag({ label }: { label: string }) {
  return (
    <span
      style={{
        background: '#1a1a1a',
        border: '1px solid #222222',
        borderRadius: '100px',
        padding: '3px 10px',
        fontSize: '11px',
        color: '#a09a92',
      }}
    >
      {label}
    </span>
  )
}

/* ═══════════════════════════════════════════════
   ZONE 1 — Featured Tonight (no search yet)
═══════════════════════════════════════════════ */

const ALSO_AVAILABLE = [
  RESTAURANTS[1], // Sol Nest
  RESTAURANTS[2], // The Olive Press
  RESTAURANTS[4], // Spice Route
]

function FeaturedCard({ restaurant }: { restaurant: Restaurant }) {
  const gradient = getCuisineGradient(restaurant.cuisine_type)
  const emoji = getCuisineEmoji(restaurant.cuisine_type)

  return (
    <article
      className="overflow-hidden cursor-pointer transition-colors duration-200"
      style={{
        background: '#111111',
        border: '1px solid #222222',
        borderRadius: '14px',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#c9a96e')}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#222222')}
    >
      {/* Visual area */}
      <div
        className="flex items-center justify-center"
        style={{ height: '160px', background: gradient }}
        aria-hidden="true"
      >
        <span style={{ fontSize: '52px' }}>{emoji}</span>
      </div>
      {/* Content */}
      <div style={{ padding: '20px' }}>
        <p style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#504a44' }}>
          {restaurant.cuisine_type} &middot; {restaurant.neighborhood}
        </p>
        <h3 className="font-serif italic" style={{ fontSize: '22px', color: '#f7f3ee', marginTop: '6px' }}>
          {restaurant.name}
        </h3>
        <p style={{ fontSize: '12px', color: '#a09a92', marginTop: '6px' }}>
          {restaurant.description}
        </p>
        <p style={{ fontSize: '12px', color: '#c9a96e', marginTop: '8px' }}>
          From {priceSymbols(restaurant.price_range)}
        </p>
        <button
          className="w-full transition-colors duration-150"
          style={{
            marginTop: '16px',
            height: '38px',
            background: 'transparent',
            border: '1px solid #2d2d2d',
            borderRadius: '9px',
            fontSize: '13px',
            color: '#a09a92',
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = '#c9a96e'
            e.currentTarget.style.color = '#c9a96e'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = '#2d2d2d'
            e.currentTarget.style.color = '#a09a92'
          }}
        >
          Reserve &rarr;
        </button>
      </div>
    </article>
  )
}

function SmallCard({ restaurant }: { restaurant: Restaurant }) {
  const emoji = getCuisineEmoji(restaurant.cuisine_type)
  return (
    <article
      className="flex gap-3.5 cursor-pointer transition-colors duration-200"
      style={{
        padding: '14px',
        background: '#111111',
        border: '1px solid #1e1e1e',
        borderRadius: '12px',
        marginBottom: '10px',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#c9a96e')}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#1e1e1e')}
    >
      <div
        className="flex items-center justify-center flex-shrink-0"
        style={{ width: '44px', height: '44px', background: '#1a1a1a', borderRadius: '8px', fontSize: '24px' }}
        aria-hidden="true"
      >
        {emoji}
      </div>
      <div>
        <p style={{ fontSize: '13px', fontWeight: 500, color: '#f7f3ee' }}>{restaurant.name}</p>
        <p style={{ fontSize: '11px', color: '#a09a92', marginTop: '2px' }}>
          {restaurant.cuisine_type} &middot; {restaurant.neighborhood}
        </p>
        <p style={{ fontSize: '11px', color: '#c9a96e', marginTop: '1px' }}>
          {priceSymbols(restaurant.price_range)}
        </p>
      </div>
    </article>
  )
}

function Zone1() {
  return (
    <div>
      <MicroHeading>Featured Tonight</MicroHeading>
      <FeaturedCard restaurant={RESTAURANTS[0]} />
      <div style={{ marginTop: '28px', marginBottom: '0' }}>
        <MicroHeading>Also Available Tonight</MicroHeading>
        {ALSO_AVAILABLE.map((r) => <SmallCard key={r.id} restaurant={r} />)}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════
   ZONE 2 — Search Results
═══════════════════════════════════════════════ */

const MATCH_EXPLANATIONS: Record<string, string> = {
  'rest-001': 'Quiet outdoor seating and gluten-free kitchen in Uptown — matches your party size and Saturday evening preference.',
  'rest-004': 'Historic French fine dining in Downtown — intimate, quiet, and perfect for a romantic evening.',
  'rest-002': 'Romantic waterfront setting in Harbor District — serene and ideal for a dinner for two.',
}

function TopResultCard({
  restaurant,
  score,
  explanation,
  onCheckAvailability,
}: {
  restaurant: Restaurant
  score: number
  explanation: string
  onCheckAvailability: () => void
}) {
  const gradient = getCuisineGradient(restaurant.cuisine_type)
  const emoji = getCuisineEmoji(restaurant.cuisine_type)

  return (
    <article
      className="overflow-hidden cursor-pointer transition-colors duration-200"
      style={{
        background: '#111111',
        border: '1px solid #2d2d2d',
        borderRadius: '14px',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#c9a96e')}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#2d2d2d')}
    >
      {/* Image area */}
      <div
        className="relative flex items-center justify-center"
        style={{ height: '120px', background: gradient }}
        aria-hidden="true"
      >
        <span style={{ fontSize: '52px' }}>{emoji}</span>
        <span
          className="absolute"
          style={{
            top: '12px',
            right: '12px',
            background: 'rgba(201,169,110,0.15)',
            border: '1px solid rgba(201,169,110,0.3)',
            borderRadius: '100px',
            padding: '3px 10px',
            fontSize: '10px',
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            color: '#c9a96e',
          }}
        >
          Best Match
        </span>
      </div>

      {/* Content */}
      <div style={{ padding: '18px' }}>
        <p style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#504a44', marginBottom: '6px' }}>
          {restaurant.cuisine_type} &middot; {restaurant.neighborhood}
        </p>
        <h3 className="font-serif italic" style={{ fontSize: '20px', color: '#f7f3ee' }}>
          {restaurant.name}
        </h3>
        <p style={{ fontSize: '12px', color: '#c9a96e', marginTop: '4px' }}>
          {priceSymbols(restaurant.price_range)}
        </p>

        {/* Match reason box */}
        <div
          style={{
            marginTop: '12px',
            background: '#0e0e0e',
            borderLeft: '2px solid #c9a96e',
            borderRadius: '0 8px 8px 0',
            padding: '10px 14px',
            fontSize: '12px',
            color: '#a09a92',
            lineHeight: 1.6,
          }}
        >
          <span style={{ color: '#c9a96e' }}>Why we chose this: </span>
          {explanation}
        </div>

        {/* Ambiance tags */}
        <div className="flex flex-wrap gap-1.5 mt-3">
          {restaurant.ambiance_tags.slice(0, 3).map((t) => (
            <Tag key={t} label={tagLabel(t)} />
          ))}
        </div>

        {/* Match score bar */}
        <div className="flex items-center gap-2.5 mt-3.5">
          <span style={{ fontSize: '11px', color: '#504a44' }}>Match</span>
          <div style={{ flex: 1, height: '2px', background: '#1e1e1e', borderRadius: '2px' }}>
            <div
              style={{
                height: '100%',
                width: `${score * 100}%`,
                background: '#c9a96e',
                borderRadius: '2px',
                transition: 'width 600ms ease',
              }}
            />
          </div>
          <span style={{ fontSize: '11px', color: '#c9a96e' }}>{Math.round(score * 100)}%</span>
        </div>

        {/* CTA */}
        <button
          onClick={onCheckAvailability}
          className="w-full transition-colors duration-150"
          style={{
            marginTop: '16px',
            height: '40px',
            background: '#c9a96e',
            color: '#080808',
            borderRadius: '9px',
            fontSize: '13px',
            fontWeight: 500,
            border: 'none',
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = '#e8cc9a')}
          onMouseLeave={(e) => (e.currentTarget.style.background = '#c9a96e')}
        >
          Check Availability
        </button>
      </div>
    </article>
  )
}

function SecondaryResultCard({
  restaurant,
  onSelect,
}: {
  restaurant: Restaurant
  onSelect: () => void
}) {
  const emoji = getCuisineEmoji(restaurant.cuisine_type)
  return (
    <article
      className="flex gap-3.5 cursor-pointer transition-colors duration-200"
      style={{
        padding: '14px',
        background: '#111111',
        border: '1px solid #1e1e1e',
        borderRadius: '12px',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#c9a96e')}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#1e1e1e')}
    >
      <div
        className="flex items-center justify-center flex-shrink-0"
        style={{ width: '44px', height: '44px', background: '#1a1a1a', borderRadius: '8px', fontSize: '22px' }}
        aria-hidden="true"
      >
        {emoji}
      </div>
      <div className="flex-1 min-w-0">
        <p style={{ fontSize: '13px', fontWeight: 500, color: '#f7f3ee' }}>{restaurant.name}</p>
        <p style={{ fontSize: '11px', color: '#a09a92', marginTop: '2px' }}>
          {restaurant.cuisine_type} &middot; {restaurant.neighborhood}
        </p>
        <div className="flex flex-wrap gap-1 mt-1.5">
          {restaurant.ambiance_tags.slice(0, 2).map((t) => <Tag key={t} label={tagLabel(t)} />)}
        </div>
      </div>
      <div className="flex-shrink-0 flex items-start pt-0.5">
        <button
          onClick={onSelect}
          className="transition-colors duration-150"
          style={{
            height: '28px',
            padding: '0 10px',
            background: 'transparent',
            border: '1px solid #2d2d2d',
            borderRadius: '7px',
            fontSize: '11px',
            color: '#a09a92',
            cursor: 'pointer',
            fontFamily: 'inherit',
            whiteSpace: 'nowrap',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = '#c9a96e'
            e.currentTarget.style.color = '#c9a96e'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = '#2d2d2d'
            e.currentTarget.style.color = '#a09a92'
          }}
        >
          View &rarr;
        </button>
      </div>
    </article>
  )
}

function Zone2({
  results,
  onCheckAvailability,
  onSelectRestaurant,
}: {
  results: Restaurant[]
  onCheckAvailability: (r: Restaurant) => void
  onSelectRestaurant: (r: Restaurant) => void
}) {
  const [top, ...rest] = results
  if (!top) return null
  const explanation = MATCH_EXPLANATIONS[top.id] ?? 'Best match for your preferences and availability.'

  return (
    <div>
      <MicroHeading>We Found for You</MicroHeading>
      <p style={{ fontSize: '12px', color: '#a09a92', marginBottom: '20px', marginTop: '-14px' }}>
        {results.length} restaurant{results.length !== 1 ? 's' : ''} match your request
      </p>
      <TopResultCard
        restaurant={top}
        score={0.85}
        explanation={explanation}
        onCheckAvailability={() => onCheckAvailability(top)}
      />
      <div className="flex flex-col gap-2.5 mt-2.5">
        {rest.slice(0, 2).map((r) => (
          <SecondaryResultCard key={r.id} restaurant={r} onSelect={() => onSelectRestaurant(r)} />
        ))}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════
   ZONE 3 — Reservation Summary (always visible)
═══════════════════════════════════════════════ */

function ReservationRow({ icon, label, value }: { icon: string; label: string; value: string | null }) {
  return (
    <div
      className="flex items-center justify-between"
      style={{ padding: '11px 0', borderBottom: '1px solid #151515' }}
    >
      <span
        className="flex items-center gap-2"
        style={{ fontSize: '12px', color: '#504a44' }}
      >
        <span aria-hidden="true">{icon}</span>
        {label}
      </span>
      {value ? (
        <span style={{ fontSize: '12px', fontWeight: 500, color: '#f7f3ee' }}>{value}</span>
      ) : (
        <span style={{ fontSize: '12px', color: '#222222' }}>&mdash;</span>
      )}
    </div>
  )
}

function Zone3({ fields }: { fields: AppState['bookingFields'] }) {
  return (
    <div>
      <MicroHeading>Your Reservation</MicroHeading>
      <ReservationRow icon="👤" label="Party Size" value={fields.partySize} />
      <ReservationRow icon="📅" label="Date"       value={fields.date} />
      <ReservationRow icon="🕐" label="Time"       value={fields.time} />
      <ReservationRow icon="✨" label="Occasion"   value={fields.occasion} />
    </div>
  )
}

/* ═══════════════════════════════════════════════
   CONTEXT PANEL — outer shell
═══════════════════════════════════════════════ */

interface ContextPanelProps {
  state: AppState
  onCheckAvailability: (restaurant: Restaurant) => void
  onSelectRestaurant: (restaurant: Restaurant) => void
}

export function ContextPanel({ state, onCheckAvailability, onSelectRestaurant }: ContextPanelProps) {
  const { searchResults, bookingFields } = state
  const hasResults = searchResults.length > 0

  return (
    <aside
      aria-label="Discovery panel"
      className="overflow-y-auto"
      style={{
        width: '45%',
        background: '#0d0d0d',
        borderLeft: '1px solid #1a1a1a',
        position: 'sticky',
        top: '60px',
        height: 'calc(100vh - 60px)',
        padding: '32px 28px',
        flexShrink: 0,
      }}
    >
      {/* Zone 1 or Zone 2 */}
      {hasResults ? (
        <Zone2
          results={searchResults}
          onCheckAvailability={onCheckAvailability}
          onSelectRestaurant={onSelectRestaurant}
        />
      ) : (
        <Zone1 />
      )}

      <Divider />

      {/* Zone 3 always present */}
      <Zone3 fields={bookingFields} />
    </aside>
  )
}
