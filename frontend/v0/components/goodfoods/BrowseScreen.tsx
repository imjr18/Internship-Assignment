'use client'

import { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, X, Check } from 'lucide-react'
import {
  RESTAURANTS,
  getCuisineEmoji,
  getCuisineGradient,
  priceSymbols,
  tagLabel,
  DIETARY_LABELS,
} from '@/lib/mock-data'
import type { Restaurant } from '@/lib/types'

/* ──────────────────────────────────────────────
   Filter data
────────────────────────────────────────────── */

const ALL_CUISINES = [...new Set(RESTAURANTS.map((r) => r.cuisine_type))].sort()
const ALL_NEIGHBORHOODS = [...new Set(RESTAURANTS.map((r) => r.neighborhood))].sort()
const PRICE_TIERS = [1, 2, 3, 4]

/* ──────────────────────────────────────────────
   Dropdown multi-select
────────────────────────────────────────────── */

function Dropdown({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: string[]
  value: string[]
  onChange: (v: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const active = value.length > 0

  function toggle(opt: string) {
    onChange(value.includes(opt) ? value.filter((v) => v !== opt) : [...value, opt])
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 transition-colors duration-150"
        style={{
          height: '36px',
          padding: '0 14px',
          background: active ? '#1e1a0f' : '#111111',
          border: `1px solid ${active ? '#c9a96e' : '#222222'}`,
          borderRadius: '9px',
          fontSize: '13px',
          color: active ? '#c9a96e' : '#a09a92',
          cursor: 'pointer',
          fontFamily: 'inherit',
          whiteSpace: 'nowrap',
        }}
      >
        {active ? `${label} (${value.length})` : label}
        <ChevronDown size={13} aria-hidden="true" />
      </button>

      <AnimatePresence>
        {open && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setOpen(false)}
              aria-hidden="true"
            />
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.12 }}
              className="absolute left-0 top-full mt-1 z-50 overflow-y-auto"
              style={{
                background: '#111111',
                border: '1px solid #2d2d2d',
                borderRadius: '10px',
                padding: '6px',
                minWidth: '180px',
                maxHeight: '240px',
              }}
            >
              {options.map((opt) => {
                const checked = value.includes(opt)
                return (
                  <button
                    key={opt}
                    onClick={() => toggle(opt)}
                    className="w-full flex items-center gap-2 text-left px-3 py-2 rounded transition-colors duration-100"
                    style={{
                      fontSize: '13px',
                      color: checked ? '#c9a96e' : '#a09a92',
                      background: checked ? '#1e1a0f' : 'transparent',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                    }}
                    onMouseEnter={(e) => { if (!checked) e.currentTarget.style.background = '#1a1a1a' }}
                    onMouseLeave={(e) => { if (!checked) e.currentTarget.style.background = 'transparent' }}
                  >
                    <span style={{ width: '12px', flexShrink: 0 }}>
                      {checked && <Check size={12} aria-hidden="true" />}
                    </span>
                    {opt}
                  </button>
                )
              })}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ──────────────────────────────────────────────
   Filter bar
────────────────────────────────────────────── */

interface FilterBarProps {
  cuisines: string[]
  neighborhoods: string[]
  prices: number[]
  count: number
  total: number
  onCuisineChange: (v: string[]) => void
  onNeighborhoodChange: (v: string[]) => void
  onPriceChange: (v: number[]) => void
}

function FilterBar({
  cuisines, neighborhoods, prices, count, total,
  onCuisineChange, onNeighborhoodChange, onPriceChange,
}: FilterBarProps) {
  const isFiltered = cuisines.length > 0 || neighborhoods.length > 0 || prices.length > 0

  function togglePrice(p: number) {
    onPriceChange(prices.includes(p) ? prices.filter((v) => v !== p) : [...prices, p])
  }

  return (
    <div
      className="flex items-center gap-3 flex-wrap"
      style={{
        position: 'sticky',
        top: '60px',
        zIndex: 30,
        background: '#080808',
        borderBottom: '1px solid #1a1a1a',
        padding: '16px 48px',
      }}
    >
      <Dropdown
        label="All Cuisines"
        options={ALL_CUISINES}
        value={cuisines}
        onChange={onCuisineChange}
      />
      <Dropdown
        label="All Neighborhoods"
        options={ALL_NEIGHBORHOODS}
        value={neighborhoods}
        onChange={onNeighborhoodChange}
      />

      {/* Price segmented control */}
      <div className="flex" style={{ border: '1px solid #222222', borderRadius: '9px', overflow: 'hidden' }}>
        {PRICE_TIERS.map((p) => {
          const active = prices.includes(p)
          return (
            <button
              key={p}
              onClick={() => togglePrice(p)}
              style={{
                height: '36px',
                minWidth: '44px',
                fontSize: '12px',
                cursor: 'pointer',
                background: active ? '#1e1a0f' : '#111111',
                borderLeft: p !== 1 ? '1px solid #222222' : 'none',
                color: active ? '#c9a96e' : '#a09a92',
                fontFamily: 'inherit',
                transition: 'background 150ms, color 150ms',
              }}
            >
              {'$'.repeat(p)}
            </button>
          )
        })}
      </div>

      {isFiltered && (
        <button
          onClick={() => { onCuisineChange([]); onNeighborhoodChange([]); onPriceChange([]) }}
          style={{ fontSize: '12px', color: '#504a44', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#c9a96e')}
          onMouseLeave={(e) => (e.currentTarget.style.color = '#504a44')}
        >
          Clear
        </button>
      )}

      {/* Count — right side */}
      <span style={{ marginLeft: 'auto', fontSize: '13px', color: '#504a44' }}>
        {isFiltered ? `${count} of ` : ''}{total} locations
      </span>
    </div>
  )
}

/* ──────────────────────────────────────────────
   Restaurant grid card
────────────────────────────────────────────── */

function GridCard({ restaurant, onClick }: { restaurant: Restaurant; onClick: () => void }) {
  const emoji = getCuisineEmoji(restaurant.cuisine_type)
  const gradient = getCuisineGradient(restaurant.cuisine_type)

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
      aria-label={`View details for ${restaurant.name}`}
      className="overflow-hidden cursor-pointer transition-all duration-200"
      style={{
        background: '#111111',
        border: '1px solid #1e1e1e',
        borderRadius: '14px',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = '#c9a96e'
        e.currentTarget.style.transform = 'translateY(-3px)'
        e.currentTarget.style.boxShadow = '0 12px 40px rgba(0,0,0,0.4)'
        const link = e.currentTarget.querySelector('.reserve-text') as HTMLElement | null
        if (link) link.style.color = '#c9a96e'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = '#1e1e1e'
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = 'none'
        const link = e.currentTarget.querySelector('.reserve-text') as HTMLElement | null
        if (link) link.style.color = '#504a44'
      }}
    >
      {/* Image area */}
      <div
        className="relative flex items-center justify-center"
        style={{ height: '180px', background: gradient }}
        aria-hidden="true"
      >
        <span style={{ fontSize: '52px' }}>{emoji}</span>
        <span
          className="absolute"
          style={{
            top: 0,
            right: 0,
            background: 'rgba(0,0,0,0.75)',
            borderRadius: '0 14px 0 10px',
            padding: '6px 12px',
            fontSize: '11px',
            color: '#c9a96e',
          }}
        >
          {priceSymbols(restaurant.price_range)}
        </span>
      </div>

      {/* Body */}
      <div style={{ padding: '20px' }}>
        <p style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#504a44', marginBottom: '8px' }}>
          {restaurant.cuisine_type} &middot; {restaurant.neighborhood}
        </p>
        <h3 className="font-serif italic" style={{ fontSize: '20px', color: '#f7f3ee' }}>
          {restaurant.name}
        </h3>
        <p
          style={{
            fontSize: '13px',
            color: '#a09a92',
            marginTop: '6px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {restaurant.description}
        </p>

        {/* Tags */}
        <div className="flex flex-wrap gap-1.5 mt-3">
          {restaurant.ambiance_tags.slice(0, 3).map((t) => (
            <span
              key={t}
              style={{
                background: '#1a1a1a',
                border: '1px solid #222222',
                borderRadius: '100px',
                padding: '3px 10px',
                fontSize: '11px',
                color: '#a09a92',
              }}
            >
              {tagLabel(t)}
            </span>
          ))}
        </div>

        {/* Footer */}
        <div
          className="flex justify-between items-center"
          style={{ marginTop: '16px', paddingTop: '14px', borderTop: '1px solid #151515' }}
        >
          <span style={{ fontSize: '12px', color: '#504a44' }}>
            Up to {restaurant.total_capacity} guests
          </span>
          <span className="reserve-text" style={{ fontSize: '12px', color: '#504a44', transition: 'color 200ms' }}>
            Reserve &rarr;
          </span>
        </div>
      </div>
    </article>
  )
}

/* ──────────────────────────────────────────────
   Bottom sheet detail
────────────────────────────────────────────── */

function BottomSheet({
  restaurant,
  onClose,
  onBook,
}: {
  restaurant: Restaurant | null
  onClose: () => void
  onBook: (r: Restaurant) => void
}) {
  return (
    <AnimatePresence>
      {restaurant && (
        <>
          {/* Overlay */}
          <motion.div
            key="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0"
            style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)', zIndex: 90 }}
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Sheet */}
          <motion.div
            key="sheet"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ duration: 0.35, ease: [0.32, 0.72, 0, 1] }}
            className="fixed bottom-0 left-0 right-0 overflow-y-auto"
            style={{
              background: '#111111',
              borderTop: '1px solid #2d2d2d',
              borderRadius: '20px 20px 0 0',
              maxHeight: '85vh',
              zIndex: 100,
              padding: '32px 40px',
            }}
            role="dialog"
            aria-label={`Details for ${restaurant.name}`}
          >
            {/* Drag handle */}
            <div
              style={{
                width: '32px',
                height: '3px',
                background: '#2d2d2d',
                borderRadius: '100px',
                margin: '-16px auto 24px',
              }}
              aria-hidden="true"
            />

            {/* Two-column layout */}
            <div className="flex gap-8">
              {/* Left — restaurant detail (60%) */}
              <div style={{ flex: '0 0 60%' }}>
                <span style={{ fontSize: '48px' }} aria-hidden="true">
                  {getCuisineEmoji(restaurant.cuisine_type)}
                </span>
                <h2
                  className="font-serif italic"
                  style={{ fontSize: '28px', color: '#f7f3ee', marginTop: '12px' }}
                >
                  {restaurant.name}
                </h2>
                <p style={{ fontSize: '13px', color: '#a09a92', marginTop: '4px' }}>
                  {restaurant.cuisine_type} &middot; {restaurant.neighborhood}
                </p>
                <p style={{ fontSize: '13px', color: '#c9a96e', marginTop: '2px' }}>
                  {priceSymbols(restaurant.price_range)}
                </p>

                {/* About */}
                <div style={{ marginTop: '24px' }}>
                  <p className="uppercase" style={{ fontSize: '10px', letterSpacing: '0.12em', color: '#504a44', marginBottom: '8px' }}>About</p>
                  <p style={{ fontSize: '14px', color: '#a09a92', lineHeight: 1.7 }}>
                    {restaurant.description}
                  </p>
                </div>

                {/* Hours */}
                <div style={{ marginTop: '20px' }}>
                  <p className="uppercase" style={{ fontSize: '10px', letterSpacing: '0.12em', color: '#504a44', marginBottom: '8px' }}>Hours</p>
                  <p style={{ fontSize: '14px', color: '#f7f3ee' }}>
                    {restaurant.operating_hours.open} &rarr; {restaurant.operating_hours.close}
                  </p>
                </div>

                {/* Atmosphere */}
                {restaurant.ambiance_tags.length > 0 && (
                  <div style={{ marginTop: '20px' }}>
                    <p className="uppercase" style={{ fontSize: '10px', letterSpacing: '0.12em', color: '#504a44', marginBottom: '8px' }}>Atmosphere</p>
                    <div className="flex flex-wrap gap-2">
                      {restaurant.ambiance_tags.map((t) => (
                        <span
                          key={t}
                          style={{
                            background: '#1a1a1a',
                            border: '1px solid #222222',
                            borderRadius: '100px',
                            padding: '3px 10px',
                            fontSize: '11px',
                            color: '#a09a92',
                          }}
                        >
                          {tagLabel(t)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Dietary */}
                {restaurant.dietary_certifications.length > 0 && (
                  <div style={{ marginTop: '20px' }}>
                    <p className="uppercase" style={{ fontSize: '10px', letterSpacing: '0.12em', color: '#504a44', marginBottom: '8px' }}>Dietary</p>
                    <div className="flex flex-col gap-2">
                      {restaurant.dietary_certifications.map((cert) => {
                        const info = DIETARY_LABELS[cert]
                        if (!info) return null
                        return (
                          <span key={cert} className="flex items-center gap-2">
                            <span
                              style={{ width: '6px', height: '6px', borderRadius: '50%', background: info.color, display: 'inline-block', flexShrink: 0 }}
                              aria-hidden="true"
                            />
                            <span style={{ fontSize: '14px', color: '#a09a92' }}>{info.label}</span>
                          </span>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Right — booking card (40%) */}
              <div style={{ flex: '0 0 calc(40% - 32px)' }}>
                <div
                  style={{
                    position: 'sticky',
                    top: '24px',
                    background: '#0d0d0d',
                    border: '1px solid #1e1e1e',
                    borderRadius: '14px',
                    padding: '24px',
                  }}
                >
                  <h3
                    className="font-serif italic"
                    style={{ fontSize: '20px', color: '#f7f3ee', marginBottom: '16px' }}
                  >
                    Reserve a table
                  </h3>
                  <p style={{ fontSize: '12px', color: '#a09a92', marginBottom: '20px' }}>
                    Seats up to {restaurant.total_capacity} guests
                  </p>
                  <button
                    onClick={() => onBook(restaurant)}
                    className="w-full transition-colors duration-150"
                    style={{
                      height: '46px',
                      background: '#c9a96e',
                      color: '#080808',
                      borderRadius: '9px',
                      fontSize: '14px',
                      fontWeight: 500,
                      border: 'none',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = '#e8cc9a')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = '#c9a96e')}
                  >
                    Book with Sage &rarr;
                  </button>
                  <p
                    className="text-center"
                    style={{ fontSize: '12px', color: '#504a44', lineHeight: 1.6, marginTop: '12px' }}
                  >
                    Tell Sage you&apos;d like to dine at {restaurant.name} and she&apos;ll find the perfect table for you.
                  </p>
                </div>
              </div>
            </div>

            {/* Close button */}
            <button
              onClick={onClose}
              aria-label="Close"
              className="absolute flex items-center justify-center transition-colors duration-150"
              style={{
                top: '28px',
                right: '40px',
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                background: '#1a1a1a',
                border: '1px solid #2d2d2d',
                color: '#a09a92',
                cursor: 'pointer',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = '#f7f3ee')}
              onMouseLeave={(e) => (e.currentTarget.style.color = '#a09a92')}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

/* ──────────────────────────────────────────────
   BrowseScreen
────────────────────────────────────────────── */

interface BrowseScreenProps {
  onBookRestaurant: (restaurant: Restaurant) => void
  defaultOpenId?: string | null
}

export function BrowseScreen({ onBookRestaurant, defaultOpenId = null }: BrowseScreenProps) {
  const [cuisines, setCuisines] = useState<string[]>([])
  const [neighborhoods, setNeighborhoods] = useState<string[]>([])
  const [prices, setPrices] = useState<number[]>([])
  const [open, setOpen] = useState<Restaurant | null>(
    defaultOpenId ? (RESTAURANTS.find((r) => r.id === defaultOpenId) ?? null) : null
  )

  const filtered = useMemo(
    () =>
      RESTAURANTS.filter((r) => {
        if (cuisines.length > 0 && !cuisines.includes(r.cuisine_type)) return false
        if (neighborhoods.length > 0 && !neighborhoods.includes(r.neighborhood)) return false
        if (prices.length > 0 && !prices.includes(r.price_range)) return false
        return true
      }),
    [cuisines, neighborhoods, prices]
  )

  function handleBook(r: Restaurant) {
    setOpen(null)
    onBookRestaurant(r)
  }

  return (
    <div style={{ paddingTop: '60px' }}>
      {/* Hero */}
      <section
        className="flex flex-col items-center justify-center text-center"
        style={{
          height: '280px',
          background: 'linear-gradient(160deg, #0f0d08, #080808)',
        }}
      >
        <p
          className="uppercase"
          style={{ fontSize: '11px', letterSpacing: '0.2em', color: '#504a44', marginBottom: '16px' }}
        >
          Our Locations
        </p>
        <h1
          className="font-serif italic text-balance"
          style={{ fontSize: '44px', color: '#f7f3ee', lineHeight: 1.2 }}
        >
          75 restaurants. One reservation.
        </h1>
        <p style={{ fontSize: '16px', color: '#a09a92', marginTop: '12px' }}>
          Find your perfect GoodFoods location.
        </p>
      </section>

      {/* Filter bar */}
      <FilterBar
        cuisines={cuisines}
        neighborhoods={neighborhoods}
        prices={prices}
        count={filtered.length}
        total={RESTAURANTS.length}
        onCuisineChange={setCuisines}
        onNeighborhoodChange={setNeighborhoods}
        onPriceChange={setPrices}
      />

      {/* Grid */}
      <section
        style={{ padding: '40px 48px' }}
        aria-label="Restaurant listings"
      >
        {filtered.length > 0 ? (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '20px',
            }}
          >
            {filtered.map((r) => (
              <GridCard key={r.id} restaurant={r} onClick={() => setOpen(r)} />
            ))}
          </div>
        ) : (
          <div className="text-center" style={{ padding: '80px 0' }}>
            <p style={{ fontSize: '16px', color: '#504a44' }}>No restaurants match your filters.</p>
            <button
              onClick={() => { setCuisines([]); setNeighborhoods([]); setPrices([]) }}
              style={{
                marginTop: '16px',
                fontSize: '13px',
                color: '#c9a96e',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              Clear all filters
            </button>
          </div>
        )}
      </section>

      {/* Bottom sheet */}
      <BottomSheet restaurant={open} onClose={() => setOpen(null)} onBook={handleBook} />
    </div>
  )
}
