'use client'

import { DIETARY_LABELS, PRICE_SYMBOLS } from '@/lib/mock-data'
import type { Restaurant } from '@/lib/types'

function DietaryDot({ cert }: { cert: string }) {
  const info = DIETARY_LABELS[cert]
  if (!info) return null
  return (
    <span className="flex items-center gap-1">
      <span
        style={{
          width: '5px',
          height: '5px',
          borderRadius: '50%',
          background: info.color,
          display: 'inline-block',
          flexShrink: 0,
        }}
        aria-hidden="true"
      />
      <span style={{ fontSize: '10px', color: info.color }}>{info.label}</span>
    </span>
  )
}

function AmbianceTag({ tag }: { tag: string }) {
  const label = tag.replace(/_/g, ' ')
  return (
    <span
      style={{
        background: '#1e1e1e',
        border: '1px solid #2a2a2a',
        borderRadius: '20px',
        padding: '2px 8px',
        fontSize: '11px',
        color: '#9a9589',
      }}
    >
      {label}
    </span>
  )
}

interface TopMatchCardProps {
  restaurant: Restaurant
  score: number
  explanation: string
  onCheckAvailability: () => void
}

export function TopMatchCard({
  restaurant,
  score,
  explanation,
  onCheckAvailability,
}: TopMatchCardProps) {
  return (
    <div
      style={{
        background: '#141414',
        border: '1px solid #2a2a2a',
        borderRadius: '12px',
        padding: '18px',
      }}
    >
      {/* TOP MATCH label */}
      <div
        className="uppercase mb-1.5"
        style={{ fontSize: '10px', letterSpacing: '0.12em', color: '#c8a96e' }}
      >
        Top Match
      </div>

      {/* Name */}
      <div style={{ fontSize: '16px', fontWeight: 600, color: '#f5f0ea' }}>
        {restaurant.name}
      </div>

      {/* Cuisine · Neighborhood */}
      <div style={{ fontSize: '12px', color: '#9a9589', marginTop: '3px' }}>
        {restaurant.cuisine_type} · {restaurant.neighborhood}
      </div>

      {/* Price */}
      <div style={{ fontSize: '12px', color: '#c8a96e', marginTop: '2px' }}>
        {PRICE_SYMBOLS(restaurant.price_range)}
      </div>

      {/* Ambiance tags */}
      <div className="flex flex-wrap gap-1 mt-1.5">
        {restaurant.ambiance_tags.slice(0, 4).map((tag) => (
          <AmbianceTag key={tag} tag={tag} />
        ))}
      </div>

      {/* Dietary certs */}
      {restaurant.dietary_certifications.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2">
          {restaurant.dietary_certifications.map((cert) => (
            <DietaryDot key={cert} cert={cert} />
          ))}
        </div>
      )}

      {/* Score bar */}
      <div className="mt-3">
        <div className="flex items-center justify-between mb-1">
          <span style={{ fontSize: '10px', color: '#4a4845' }}>Match Score</span>
          <span style={{ fontSize: '10px', color: '#c8a96e' }}>
            {Math.round(score * 100)}%
          </span>
        </div>
        <div
          style={{
            height: '3px',
            borderRadius: '2px',
            background: '#1e1e1e',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${score * 100}%`,
              background: '#c8a96e',
              borderRadius: '2px',
              transition: 'width 600ms ease',
            }}
          />
        </div>
      </div>

      {/* Explanation box */}
      <div
        style={{
          background: '#0f1200',
          borderLeft: '2px solid #c8a96e',
          borderRadius: '0 8px 8px 0',
          padding: '10px 12px',
          marginTop: '10px',
          fontSize: '12px',
          color: '#9a9589',
          lineHeight: '1.6',
        }}
      >
        <span style={{ color: '#c8a96e' }}>Matched because: </span>
        {explanation}
      </div>

      {/* CTA */}
      <button
        onClick={onCheckAvailability}
        className="w-full transition-colors duration-150"
        style={{
          marginTop: '12px',
          height: '36px',
          background: '#c8a96e',
          color: '#0a0a0a',
          borderRadius: '8px',
          fontSize: '13px',
          fontWeight: 500,
          cursor: 'pointer',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = '#d4b87e')}
        onMouseLeave={(e) => (e.currentTarget.style.background = '#c8a96e')}
      >
        Check Availability →
      </button>
    </div>
  )
}

interface SecondaryCardProps {
  restaurant: Restaurant
  onSelect: () => void
}

export function SecondaryCard({ restaurant, onSelect }: SecondaryCardProps) {
  return (
    <div
      style={{
        background: '#141414',
        border: '1px solid #2a2a2a',
        borderRadius: '12px',
        padding: '14px',
      }}
    >
      <div style={{ fontSize: '14px', fontWeight: 600, color: '#f5f0ea' }}>
        {restaurant.name}
      </div>
      <div style={{ fontSize: '12px', color: '#9a9589', marginTop: '2px' }}>
        {restaurant.cuisine_type} · {restaurant.neighborhood}
      </div>
      <div style={{ fontSize: '12px', color: '#c8a96e', marginTop: '2px' }}>
        {PRICE_SYMBOLS(restaurant.price_range)}
      </div>

      {/* Ambiance tags */}
      <div className="flex flex-wrap gap-1 mt-1.5">
        {restaurant.ambiance_tags.slice(0, 3).map((tag) => (
          <AmbianceTag key={tag} tag={tag} />
        ))}
      </div>

      {restaurant.dietary_certifications.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-1.5">
          {restaurant.dietary_certifications.map((cert) => (
            <DietaryDot key={cert} cert={cert} />
          ))}
        </div>
      )}

      <button
        onClick={onSelect}
        className="w-full transition-all duration-150 mt-3"
        style={{
          height: '32px',
          background: 'transparent',
          border: '1px solid #2a2a2a',
          borderRadius: '8px',
          fontSize: '12px',
          color: '#9a9589',
          cursor: 'pointer',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = '#c8a96e'
          e.currentTarget.style.color = '#c8a96e'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = '#2a2a2a'
          e.currentTarget.style.color = '#9a9589'
        }}
      >
        Select →
      </button>
    </div>
  )
}

interface EmptyRecommendationProps {
  text?: string
}

export function EmptyRecommendation({ text }: EmptyRecommendationProps) {
  return (
    <div
      className="text-center"
      style={{
        border: '1px dashed #242424',
        borderRadius: '12px',
        padding: '24px 20px',
      }}
    >
      <div style={{ fontSize: '24px', color: '#2a2a2a', marginBottom: '8px' }}>
        🔍
      </div>
      <div style={{ fontSize: '12px', color: '#4a4845' }}>
        {text ?? 'Restaurant recommendations will appear here'}
      </div>
    </div>
  )
}
