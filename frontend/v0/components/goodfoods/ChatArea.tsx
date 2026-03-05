'use client'

import { useEffect, useRef } from 'react'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import type { AppState } from '@/lib/types'

/* ─── Suggestion cards shown on landing ─── */

const SUGGESTIONS = [
  {
    icon: '🕯️',
    title: 'Romantic Dinner',
    desc: 'Table for two, intimate setting',
    message: "I'm looking for a romantic dinner for 2 this Saturday evening, somewhere quiet.",
  },
  {
    icon: '💼',
    title: 'Business Lunch',
    desc: 'Professional setting, private options',
    message:
      'I need a table for 4 people for a business lunch this Friday. One person needs a gluten-free kitchen.',
  },
  {
    icon: '🎉',
    title: 'Special Occasion',
    desc: 'Birthdays, anniversaries, celebrations',
    message:
      'We have a birthday celebration for 6 this Saturday evening — looking for somewhere lively and festive.',
  },
]

function LandingHero({ onSuggestion }: { onSuggestion: (msg: string) => void }) {
  return (
    <div style={{ paddingTop: '48px' }}>
      {/* Eyebrow */}
      <p
        className="uppercase"
        style={{
          fontSize: '10px',
          letterSpacing: '0.2em',
          color: '#504a44',
          marginBottom: '16px',
        }}
      >
        GoodFoods Concierge
      </p>

      {/* Main heading */}
      <h1
        className="font-serif italic text-balance"
        style={{
          fontSize: '42px',
          color: '#f7f3ee',
          lineHeight: 1.15,
          margin: 0,
        }}
      >
        Reserve your perfect evening.
      </h1>

      {/* Subheading */}
      <p
        style={{
          fontSize: '16px',
          color: '#a09a92',
          lineHeight: 1.6,
          marginTop: '12px',
          maxWidth: '420px',
        }}
      >
        Tell us what you&apos;re looking for and we&apos;ll find the perfect table across all GoodFoods locations.
      </p>

      {/* Suggestion cards */}
      <div
        className="flex gap-3 mt-10"
        role="list"
        aria-label="Booking suggestions"
      >
        {SUGGESTIONS.map((s) => (
          <button
            key={s.title}
            onClick={() => onSuggestion(s.message)}
            role="listitem"
            className="text-left transition-all duration-200 cursor-pointer"
            style={{
              flex: 1,
              background: '#111111',
              border: '1px solid #222222',
              borderRadius: '12px',
              padding: '16px',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#c9a96e'
              e.currentTarget.style.transform = 'translateY(-2px)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = '#222222'
              e.currentTarget.style.transform = 'translateY(0)'
            }}
          >
            <span style={{ fontSize: '20px' }} aria-hidden="true">{s.icon}</span>
            <p style={{ fontSize: '13px', fontWeight: 500, color: '#f7f3ee', marginTop: '8px' }}>
              {s.title}
            </p>
            <p style={{ fontSize: '12px', color: '#a09a92', marginTop: '4px' }}>
              {s.desc}
            </p>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ─── Main ChatArea ─── */

interface ChatAreaProps {
  state: AppState
  onSend: (message: string) => void
  /** When a suggestion card is clicked, prefill the input (do not send immediately) */
  onSuggestion?: (message: string) => void
  prefill?: string
}

export function ChatArea({ state, onSend, onSuggestion, prefill }: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const hasMessages = state.messages.length > 0

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [state.messages])

  return (
    <div
      className="flex flex-col"
      style={{
        height: 'calc(100vh - 60px)',
        padding: '0 48px',
        overflowY: 'auto',
        position: 'relative',
      }}
    >
      {/* Content area — either landing or messages */}
      <div className="flex-1">
        {hasMessages ? (
          <div
            className="flex flex-col gap-5"
            style={{ paddingTop: '40px', paddingBottom: '16px' }}
          >
            {state.messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
            <div ref={bottomRef} />
          </div>
        ) : (
          <LandingHero onSuggestion={onSuggestion ?? onSend} />
        )}
      </div>

      {/* Pinned chat input */}
      <ChatInput onSend={onSend} prefill={prefill} />
    </div>
  )
}
