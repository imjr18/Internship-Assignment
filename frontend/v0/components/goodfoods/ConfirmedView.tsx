'use client'

import { useState } from 'react'
import { Calendar, RotateCcw, Check } from 'lucide-react'
import type { BookingFields } from '@/lib/types'

/* ── Animated SVG checkmark ── */
function AnimatedCheck() {
  return (
    <div
      className="flex items-center justify-center"
      aria-label="Reservation confirmed"
      style={{
        width: '56px',
        height: '56px',
        borderRadius: '50%',
        background: 'linear-gradient(135deg, #1a2e1a, #0d1f0d)',
        border: '1px solid rgba(61,158,106,0.3)',
      }}
    >
      <Check size={24} color="#3d9e6a" strokeWidth={2} aria-hidden="true" />
    </div>
  )
}

/* ── Booking summary row inside the card ── */
function BookingRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div
      className="flex justify-between items-center"
      style={{ padding: '10px 0', borderBottom: '1px solid #151515' }}
    >
      <span style={{ fontSize: '12px', color: '#504a44' }}>{label}</span>
      <span style={{ fontSize: '12px', fontWeight: 500, color: '#f7f3ee' }}>{value ?? '—'}</span>
    </div>
  )
}

interface ConfirmedLeftColumnProps {
  confirmationCode: string
  bookingFields: BookingFields
  onNewReservation: () => void
}

export function ConfirmedLeftColumn({
  confirmationCode,
  bookingFields,
  onNewReservation,
}: ConfirmedLeftColumnProps) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(confirmationCode).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      className="flex flex-col items-center justify-center"
      style={{
        width: '55%',
        minHeight: 'calc(100vh - 60px)',
        padding: '48px',
      }}
    >
      {/* Gold line draw */}
      <div
        className="line-draw mb-8"
        style={{
          height: '1px',
          background: '#c9a96e',
          alignSelf: 'stretch',
        }}
      />

      {/* Checkmark */}
      <AnimatedCheck />

      {/* Heading */}
      <h2
        className="font-serif italic text-center"
        style={{ fontSize: '32px', color: '#f7f3ee', marginTop: '20px' }}
      >
        Reservation Confirmed
      </h2>

      {/* Confirmation code */}
      <p
        className="font-mono text-center"
        style={{
          fontSize: '22px',
          fontWeight: 600,
          color: '#c9a96e',
          letterSpacing: '0.1em',
          marginTop: '8px',
        }}
      >
        {confirmationCode}
      </p>

      {/* Copy button */}
      <button
        onClick={handleCopy}
        className="flex items-center gap-1.5 transition-colors duration-150 mt-1"
        style={{ fontSize: '11px', color: '#504a44', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
        onMouseEnter={(e) => (e.currentTarget.style.color = '#a09a92')}
        onMouseLeave={(e) => (e.currentTarget.style.color = '#504a44')}
      >
        {copied ? (
          <><Check size={11} /> Copied</>
        ) : (
          'Copy code'
        )}
      </button>

      {/* Booking summary card */}
      <div
        style={{
          width: '100%',
          maxWidth: '400px',
          background: '#111111',
          border: '1px solid #1e1e1e',
          borderRadius: '14px',
          padding: '24px',
          marginTop: '32px',
        }}
      >
        <BookingRow label="Restaurant" value={bookingFields.restaurant} />
        <BookingRow label="Date"       value={bookingFields.date} />
        <BookingRow label="Time"       value={bookingFields.time} />
        <BookingRow label="Guests"     value={bookingFields.partySize ? `${bookingFields.partySize} people` : null} />
      </div>

      {/* Action buttons */}
      <div style={{ width: '100%', maxWidth: '400px', marginTop: '24px' }}>
        <button
          className="w-full flex items-center justify-center gap-2 transition-colors duration-150"
          style={{
            height: '44px',
            background: 'transparent',
            border: '1px solid #2d2d2d',
            borderRadius: '9px',
            fontSize: '14px',
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
          <Calendar size={16} aria-hidden="true" />
          Add to Calendar
        </button>

        <button
          onClick={onNewReservation}
          className="w-full flex items-center justify-center gap-2 transition-colors duration-150"
          style={{
            marginTop: '10px',
            height: '44px',
            background: '#1a1a1a',
            border: '1px solid #222222',
            borderRadius: '9px',
            fontSize: '14px',
            color: '#a09a92',
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = '#2d2d2d'
            e.currentTarget.style.color = '#f7f3ee'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = '#222222'
            e.currentTarget.style.color = '#a09a92'
          }}
        >
          <RotateCcw size={14} aria-hidden="true" />
          Make Another Reservation
        </button>
      </div>

      {/* Small cancel copy */}
      <p
        className="text-center"
        style={{
          fontSize: '12px',
          color: '#504a44',
          marginTop: '20px',
          maxWidth: '360px',
          lineHeight: 1.6,
        }}
      >
        Need to cancel? Reply to your confirmation email or call your GoodFoods location directly.
      </p>
    </div>
  )
}

/* ── Right panel during confirmation ── */
interface ConfirmedRightPanelProps {
  bookingFields: BookingFields
}

export function ConfirmedRightPanel({ bookingFields }: ConfirmedRightPanelProps) {
  return (
    <aside
      aria-label="Confirmed restaurant detail"
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
      {/* Section heading */}
      <p
        className="uppercase"
        style={{ fontSize: '10px', letterSpacing: '0.15em', color: '#504a44', marginBottom: '20px' }}
      >
        Your Table is Ready
      </p>

      {/* Restaurant card */}
      <div
        style={{
          background: '#111111',
          border: '1px solid #222222',
          borderRadius: '14px',
          overflow: 'hidden',
        }}
      >
        <div
          className="flex items-center justify-center"
          style={{ height: '120px', background: 'linear-gradient(160deg, #1a1400, #0d0d0d)' }}
          aria-hidden="true"
        >
          <span style={{ fontSize: '44px' }}>🍜</span>
        </div>
        <div style={{ padding: '20px' }}>
          <p style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#504a44' }}>
            Japanese &middot; Uptown
          </p>
          <h3 className="font-serif italic" style={{ fontSize: '22px', color: '#f7f3ee', marginTop: '6px' }}>
            {bookingFields.restaurant ?? 'Amber Kitchen'}
          </h3>
          <p style={{ fontSize: '12px', color: '#3d9e6a', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Check size={12} aria-hidden="true" /> Reservation confirmed
          </p>
        </div>
      </div>

      {/* Location info */}
      <div style={{ marginTop: '24px' }}>
        <p className="uppercase" style={{ fontSize: '10px', letterSpacing: '0.15em', color: '#504a44', marginBottom: '10px' }}>
          Location
        </p>
        <p style={{ fontSize: '13px', color: '#a09a92', lineHeight: 1.7 }}>
          142 Uptown Boulevard<br />New York, NY 10001
        </p>
      </div>

      <div style={{ height: '1px', background: '#1a1a1a', margin: '20px 0' }} />

      {/* Hours */}
      <div>
        <p className="uppercase" style={{ fontSize: '10px', letterSpacing: '0.15em', color: '#504a44', marginBottom: '10px' }}>
          Hours
        </p>
        <p style={{ fontSize: '13px', color: '#f7f3ee' }}>17:00 &rarr; 23:30</p>
      </div>

      <div style={{ height: '1px', background: '#1a1a1a', margin: '20px 0' }} />

      {/* Confirmed fields */}
      <p className="uppercase" style={{ fontSize: '10px', letterSpacing: '0.15em', color: '#504a44', marginBottom: '16px' }}>
        Your Reservation
      </p>
      {[
        { label: '👤 Party Size', value: bookingFields.partySize },
        { label: '📅 Date',       value: bookingFields.date },
        { label: '🕐 Time',       value: bookingFields.time },
      ].map(({ label, value }) => (
        <div
          key={label}
          className="flex items-center justify-between"
          style={{ padding: '11px 0', borderBottom: '1px solid #151515' }}
        >
          <span style={{ fontSize: '12px', color: '#504a44' }}>{label}</span>
          <span className="flex items-center gap-1.5" style={{ fontSize: '12px', fontWeight: 500, color: '#f7f3ee' }}>
            {value}
            <Check size={10} color="#3d9e6a" aria-hidden="true" />
          </span>
        </div>
      ))}
    </aside>
  )
}
