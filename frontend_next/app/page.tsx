'use client'

import { useState, useCallback, useRef } from 'react'
import { Navbar } from '@/components/goodfoods/Navbar'
import { ChatArea } from '@/components/goodfoods/ChatArea'
import { ChatInput } from '@/components/goodfoods/ChatInput'
import { ContextPanel } from '@/components/goodfoods/ContextPanel'
import { ConfirmedLeftColumn, ConfirmedRightPanel } from '@/components/goodfoods/ConfirmedView'
import { BrowseScreen } from '@/components/goodfoods/BrowseScreen'
import { buildState, INITIAL_BOOKING_FIELDS } from '@/lib/mock-data'
import { streamChat, fetchBookingState } from '@/lib/api'
import { getSessionId, resetSession } from '@/lib/session'
import type { AppState, UIState, Restaurant } from '@/lib/types'

/* ─────────────────────────────────────────
   Initial app state factory
───────────────────────────────────────── */

function makeBase(): AppState {
  return {
    screen: 'book',
    bookingState: 'GREETING',
    messages: [],
    bookingFields: { ...INITIAL_BOOKING_FIELDS },
    searchResults: [],
    confirmationCode: null,
  }
}

function mapStreamError(message: string): string {
  const lower = message.toLowerCase()
  const genericRetry = "I'm having trouble right now. Please try again in a moment."
  if (lower.includes('tokens per day') || lower.includes('tpd')) {
    return genericRetry
  }
  if (lower.includes('request too large') || lower.includes('tokens per minute')) {
    return genericRetry
  }
  if (lower.includes('rate limit') || lower.includes('429')) {
    return genericRetry
  }
  if (lower.includes('timed out') || lower.includes('timeout')) {
    return genericRetry
  }
  return genericRetry
}

/* ─────────────────────────────────────────
   Prototype state switcher
   (reviewer navigation — minimal, unobtrusive)
───────────────────────────────────────── */

const STATES: { id: UIState; label: string }[] = [
  { id: 1, label: 'Landing' },
  { id: 2, label: 'Conversation' },
  { id: 3, label: 'Confirmed' },
  { id: 4, label: 'Browse' },
]

function StateSwitcher({ active, onChange }: { active: UIState; onChange: (s: UIState) => void }) {
  return (
    <div
      className="fixed flex items-center gap-1.5 z-[200]"
      style={{
        bottom: '24px',
        left: '50%',
        transform: 'translateX(-50%)',
        background: 'rgba(8,8,8,0.92)',
        border: '1px solid #1e1e1e',
        borderRadius: '100px',
        padding: '4px 8px',
        backdropFilter: 'blur(8px)',
      }}
      aria-label="Prototype state navigator"
    >
      {STATES.map((s) => (
        <button
          key={s.id}
          onClick={() => onChange(s.id)}
          style={{
            height: '22px',
            padding: '0 10px',
            borderRadius: '100px',
            fontSize: '10px',
            cursor: 'pointer',
            background: active === s.id ? 'rgba(201,169,110,0.12)' : 'transparent',
            color: active === s.id ? '#504a44' : '#2d2d2d',
            border: `1px solid ${active === s.id ? '#2d2d2d' : 'transparent'}`,
            fontFamily: 'inherit',
            transition: 'all 150ms',
          }}
          onMouseEnter={(e) => { if (active !== s.id) e.currentTarget.style.color = '#504a44' }}
          onMouseLeave={(e) => { if (active !== s.id) e.currentTarget.style.color = '#2d2d2d' }}
        >
          {s.label}
        </button>
      ))}
    </div>
  )
}

/* ─────────────────────────────────────────
   Main Page
───────────────────────────────────────── */

export default function Page() {
  const [uiState, setUiState] = useState<UIState>(1)
  const [appState, setAppState] = useState<AppState>(() => ({
    ...makeBase(),
    ...buildState(1),
  }))
  const [prefill, setPrefill] = useState<string | undefined>(undefined)

  /* Session ID — stable per browser tab */
  const sessionIdRef = useRef<string>('')
  if (!sessionIdRef.current && typeof window !== 'undefined') {
    sessionIdRef.current = getSessionId()
  }

  /* Switch prototype state */
  function handleStateChange(s: UIState) {
    setUiState(s)
    setPrefill(undefined)
    setAppState({ ...makeBase(), ...buildState(s) })
  }

  /* Navigate between book / browse */
  const handleNavigate = useCallback((screen: 'book' | 'browse') => {
    const next: UIState = screen === 'browse' ? 4 : 1
    setUiState(next)
    setAppState({ ...makeBase(), ...buildState(next) })
  }, [])

  /* Guest sends a message — streams response from Python backend */
  const handleSend = useCallback(async (message: string) => {
    setPrefill(undefined)
    const msgId = Math.random().toString(36).slice(2)
    const sageId = Math.random().toString(36).slice(2)

    console.log('[handleSend] Starting:', message.slice(0, 50), 'session:', sessionIdRef.current)

    // Add user message + empty sage placeholder immediately
    // (no separate composing indicator — sage bubble stays empty until first token)
    setAppState((prev) => ({
      ...prev,
      messages: [
        ...prev.messages,
        { id: msgId, role: 'user' as const, content: message },
        { id: sageId, role: 'sage' as const, content: '' },
      ],
    }))

    // Accumulate text in a closure variable
    let sageText = ''
    let streamError = false

    try {
      await streamChat(
        sessionIdRef.current,
        message,
        (token) => {
          if (token.type === 'text') {
            sageText += token.content
            const snapshot = sageText  // capture for closure

            // Always use map — sage message is guaranteed to exist from the start
            setAppState((prev) => ({
              ...prev,
              messages: prev.messages.map((m) =>
                m.id === sageId
                  ? { ...m, content: snapshot }
                  : m
              ),
            }))
          }

          if (token.type === 'booking') {
            const data = token.data as Record<string, unknown>
            const dataObj = (data.data ?? data) as Record<string, unknown>
            const code = (dataObj.confirmation_code ??
              dataObj.confirmationCode) as string | undefined

            setAppState((prev) => ({
              ...prev,
              bookingState: 'COMPLETED',
              confirmationCode: code ?? null,
              bookingFields: {
                ...prev.bookingFields,
                restaurant:
                  (dataObj.restaurant_name as string) ??
                  prev.bookingFields.restaurant,
                date:
                  (dataObj.date as string) ??
                  prev.bookingFields.date,
                time:
                  (dataObj.time as string) ??
                  prev.bookingFields.time,
                partySize:
                  String(dataObj.party_size ?? prev.bookingFields.partySize ?? ''),
              },
            }))
          }

          if (token.type === 'escalated') {
            setAppState((prev) => ({
              ...prev,
              bookingState: 'ESCALATED',
            }))
          }

          if (token.type === 'done') {
            console.log('[handleSend] DONE — sageText:', sageText.length, 'chars')
            // Fetch booking state to update sidebar
            fetchBookingState(sessionIdRef.current).then(
              (state) => {
                if (!state) return
                setAppState((prev) => ({
                  ...prev,
                  bookingFields: {
                    restaurant:
                      (state.restaurant_name as string) ??
                      prev.bookingFields.restaurant,
                    partySize:
                      state.party_size
                        ? String(state.party_size)
                        : prev.bookingFields.partySize,
                    date:
                      (state.date as string) ??
                      prev.bookingFields.date,
                    time:
                      (state.time as string) ??
                      prev.bookingFields.time,
                    occasion: prev.bookingFields.occasion,
                  },
                }))
              }
            )
          }

          if (token.type === 'error') {
            if (process.env.NODE_ENV !== 'production') {
              console.warn('[handleSend] stream warning:', token.message)
            }
            streamError = true
            setAppState((prev) => ({
              ...prev,
              messages: prev.messages.map((m) =>
                m.id === sageId
                  ? { ...m, content: mapStreamError(token.message) }
                  : m
              ),
            }))
          }
        }
      )
    } catch (err) {
      if (process.env.NODE_ENV !== 'production') {
        console.warn('[handleSend] streamChat warning:', err)
      }
      if (!streamError) {
        setAppState((prev) => ({
          ...prev,
          messages: prev.messages.map((m) =>
            m.id === sageId
              ? { ...m, content: 'I hit a connection issue. Please try again in a moment.' }
              : m
          ),
        }))
      }
    }

    // If we got zero tokens and no error, remove the empty sage placeholder
    if (sageText.length === 0 && !streamError) {
      setAppState((prev) => ({
        ...prev,
        messages: prev.messages.filter((m) => m.id !== sageId),
      }))
    }
  }, [])

  /* Suggestion card clicked — prefill and focus input */
  const handleSuggestion = useCallback((message: string) => {
    setPrefill(message)
  }, [])

  /* Context panel interactions */
  const handleCheckAvailability = useCallback((restaurant: Restaurant) => {
    setAppState((prev) => ({
      ...prev,
      bookingFields: { ...prev.bookingFields, restaurant: restaurant.name },
    }))
  }, [])

  const handleSelectRestaurant = useCallback((restaurant: Restaurant) => {
    setAppState((prev) => ({
      ...prev,
      bookingFields: { ...prev.bookingFields, restaurant: restaurant.name },
    }))
  }, [])

  /* New reservation from confirmation screen */
  const handleNewReservation = useCallback(() => {
    sessionIdRef.current = resetSession()
    setUiState(1)
    setAppState({ ...makeBase(), ...buildState(1) })
    setPrefill(undefined)
  }, [])

  /* Book from browse screen — navigate to chat with restaurant pre-selected */
  const handleBookRestaurant = useCallback((restaurant: Restaurant) => {
    setUiState(1)
    setPrefill(`I'd like to make a reservation at ${restaurant.name}.`)
    setAppState({
      ...makeBase(),
      screen: 'book',
      bookingState: 'GREETING',
      bookingFields: { ...INITIAL_BOOKING_FIELDS, restaurant: restaurant.name },
    })
  }, [])


  const isConfirmed = appState.bookingState === 'COMPLETED' && appState.confirmationCode !== null

  return (
    <>
      <Navbar onNavigate={handleNavigate} />

      <main style={{ paddingTop: '60px', minHeight: '100vh' }}>
        {/* ── Browse screen (full-width) ── */}
        {appState.screen === 'browse' ? (
          <BrowseScreen
            onBookRestaurant={handleBookRestaurant}
            defaultOpenId={uiState === 4 ? 'rest-001' : null}
          />
        ) : isConfirmed ? (
          /* ── Confirmation screen (chat replaced) ── */
          <div className="flex" style={{ minHeight: 'calc(100vh - 60px)' }}>
            <ConfirmedLeftColumn
              confirmationCode={appState.confirmationCode!}
              bookingFields={appState.bookingFields}
              onNewReservation={handleNewReservation}
            />
            <ConfirmedRightPanel bookingFields={appState.bookingFields} />
          </div>
        ) : (
          /* ── Normal booking experience ── */
          <div className="flex" style={{ minHeight: 'calc(100vh - 60px)' }}>
            {/* Left column — 55% */}
            <div
              style={{
                width: '55%',
                display: 'flex',
                flexDirection: 'column',
                minHeight: 'calc(100vh - 60px)',
              }}
            >
              <ChatArea
                state={appState}
                onSend={handleSend}
                onSuggestion={handleSuggestion}
                prefill={prefill}
              />
            </div>

            {/* Right column — 45% */}
            <ContextPanel
              state={appState}
              onCheckAvailability={handleCheckAvailability}
              onSelectRestaurant={handleSelectRestaurant}
            />
          </div>
        )}
      </main>

      {/* Prototype navigator — reviewer only */}
      <StateSwitcher active={uiState} onChange={handleStateChange} />
    </>
  )
}
