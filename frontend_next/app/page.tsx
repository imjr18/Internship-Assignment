'use client'

import { useState, useCallback, useRef } from 'react'
import { Navbar } from '@/components/goodfoods/Navbar'
import { ChatArea } from '@/components/goodfoods/ChatArea'
import { ContextPanel } from '@/components/goodfoods/ContextPanel'
import { ConfirmedLeftColumn, ConfirmedRightPanel } from '@/components/goodfoods/ConfirmedView'
import { BrowseScreen } from '@/components/goodfoods/BrowseScreen'
import { INITIAL_BOOKING_FIELDS } from '@/lib/mock-data'
import { streamChat, fetchBookingState } from '@/lib/api'
import { getSessionId, resetSession } from '@/lib/session'
import type { AppState, Restaurant } from '@/lib/types'

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
  if (lower.includes('tokens per day') || lower.includes('tpd')) return genericRetry
  if (lower.includes('request too large') || lower.includes('tokens per minute')) return genericRetry
  if (lower.includes('rate limit') || lower.includes('429')) return genericRetry
  if (lower.includes('timed out') || lower.includes('timeout')) return genericRetry
  return genericRetry
}

function parseDateAndTime(reservationDatetime: unknown): { date: string | null; time: string | null } {
  if (typeof reservationDatetime !== 'string' || !reservationDatetime.includes('T')) {
    return { date: null, time: null }
  }
  const [datePart, timePart] = reservationDatetime.split('T')
  const time = timePart ? timePart.slice(0, 5) : null
  return {
    date: datePart || null,
    time: time || null,
  }
}

function extractConfirmationCode(text: string): string | null {
  const patterns = [
    /confirmation(?:\s+code)?\s*[:#-]?\s*([A-Z0-9-]{6,})/i,
    /\bcode\s*[:#-]?\s*([A-Z0-9-]{6,})\b/i,
  ]
  for (const pattern of patterns) {
    const match = text.match(pattern)
    if (match?.[1]) return match[1].toUpperCase()
  }
  return null
}

export default function Page() {
  const [appState, setAppState] = useState<AppState>(() => makeBase())
  const [prefill, setPrefill] = useState<string | undefined>(undefined)
  const [bookView, setBookView] = useState<'chat' | 'confirmed'>('chat')

  const sessionIdRef = useRef<string>('')
  const hasSentMessageRef = useRef<boolean>(false)
  if (!sessionIdRef.current && typeof window !== 'undefined') {
    sessionIdRef.current = getSessionId()
  }

  const handleHome = useCallback(() => {
    sessionIdRef.current = resetSession()
    hasSentMessageRef.current = false
    setPrefill(undefined)
    setBookView('chat')
    setAppState(makeBase())
  }, [])

  const handleBrowse = useCallback(() => {
    setAppState((prev) => ({ ...prev, screen: 'browse' }))
  }, [])

  const handleChatView = useCallback(() => {
    setBookView('chat')
    setAppState((prev) => ({ ...prev, screen: 'book' }))
  }, [])

  const handleConfirmedView = useCallback(() => {
    setBookView('confirmed')
    setAppState((prev) => ({ ...prev, screen: 'book' }))
  }, [])

  const handleSend = useCallback(async (message: string) => {
    // Ensure first message starts a fresh backend session so hidden stale
    // constraints from an older page load do not leak into this chat.
    if (!hasSentMessageRef.current) {
      sessionIdRef.current = resetSession()
      hasSentMessageRef.current = true
    }

    setPrefill(undefined)
    const msgId = Math.random().toString(36).slice(2)
    const sageId = Math.random().toString(36).slice(2)

    setAppState((prev) => ({
      ...prev,
      messages: [
        ...prev.messages,
        { id: msgId, role: 'user' as const, content: message },
        { id: sageId, role: 'sage' as const, content: '' },
      ],
    }))

    let sageText = ''
    let streamError = false

    try {
      await streamChat(sessionIdRef.current, message, (token) => {
        if (token.type === 'text') {
          sageText += token.content
          const snapshot = sageText
          const inferredCode = extractConfirmationCode(snapshot)

          setAppState((prev) => ({
            ...prev,
            messages: prev.messages.map((m) => (
              m.id === sageId ? { ...m, content: snapshot } : m
            )),
            bookingState: inferredCode ? 'COMPLETED' : prev.bookingState,
            confirmationCode: inferredCode ?? prev.confirmationCode,
          }))
        }

        if (token.type === 'booking') {
          const raw = token.data as Record<string, unknown>
          const payload = (raw.data && typeof raw.data === 'object'
            ? raw.data
            : raw) as Record<string, unknown>
          const reservation = (payload.reservation && typeof payload.reservation === 'object'
            ? payload.reservation
            : {}) as Record<string, unknown>

          const confirmationCode = (reservation.confirmation_code ??
            payload.confirmation_code ??
            payload.confirmationCode) as string | undefined

          const reservationDateTime = reservation.reservation_datetime ?? payload.reservation_datetime
          const parsed = parseDateAndTime(reservationDateTime)

          setAppState((prev) => ({
            ...prev,
            bookingState: confirmationCode ? 'COMPLETED' : prev.bookingState,
            confirmationCode: confirmationCode ?? prev.confirmationCode,
            bookingFields: {
              ...prev.bookingFields,
              restaurant:
                (payload.restaurant_name as string) ??
                (reservation.restaurant_name as string) ??
                prev.bookingFields.restaurant,
              date:
                parsed.date ??
                (payload.date as string) ??
                prev.bookingFields.date,
              time:
                parsed.time ??
                (payload.time as string) ??
                prev.bookingFields.time,
              partySize:
                String(
                  reservation.party_size ??
                  payload.party_size ??
                  prev.bookingFields.partySize ??
                  ''
                ),
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
          const inferredCode = extractConfirmationCode(sageText)
          fetchBookingState(sessionIdRef.current).then((state) => {
            const stateCode =
              state && typeof state.confirmation_code === 'string' && state.confirmation_code
                ? state.confirmation_code
                : null
            const finalCode = stateCode ?? inferredCode
            setAppState((prev) => ({
              ...prev,
              bookingState: finalCode ? 'COMPLETED' : prev.bookingState,
              confirmationCode: finalCode ?? prev.confirmationCode,
              bookingFields: {
                ...prev.bookingFields,
                restaurant:
                  (state?.restaurant_name as string) ??
                  prev.bookingFields.restaurant,
                partySize:
                  state?.party_size
                    ? String(state.party_size)
                    : prev.bookingFields.partySize,
                date:
                  (state?.date as string) ??
                  prev.bookingFields.date,
                time:
                  (state?.time as string) ??
                  prev.bookingFields.time,
              },
            }))
          }).catch(() => {
            if (!inferredCode) return
            setAppState((prev) => ({
              ...prev,
              bookingState: 'COMPLETED',
              confirmationCode: inferredCode,
            }))
          })
        }

        if (token.type === 'error') {
          if (process.env.NODE_ENV !== 'production') {
            console.warn('[handleSend] stream warning:', token.message)
          }
          streamError = true
          setAppState((prev) => ({
            ...prev,
            messages: prev.messages.map((m) => (
              m.id === sageId ? { ...m, content: mapStreamError(token.message) } : m
            )),
          }))
        }
      })
    } catch (err) {
      if (process.env.NODE_ENV !== 'production') {
        console.warn('[handleSend] streamChat warning:', err)
      }
      if (!streamError) {
        setAppState((prev) => ({
          ...prev,
          messages: prev.messages.map((m) => (
            m.id === sageId
              ? { ...m, content: 'I hit a connection issue. Please try again in a moment.' }
              : m
          )),
        }))
      }
    }

    if (sageText.length === 0 && !streamError) {
      setAppState((prev) => ({
        ...prev,
        messages: prev.messages.filter((m) => m.id !== sageId),
      }))
    }
  }, [])

  const handleSuggestion = useCallback((message: string) => {
    setPrefill(message)
  }, [])

  const handleCheckAvailability = useCallback((restaurant: Restaurant) => {
    setPrefill(`Check availability at ${restaurant.name} for a reservation.`)
    setBookView('chat')
    setAppState((prev) => ({
      ...prev,
      bookingFields: { ...prev.bookingFields, restaurant: restaurant.name },
      screen: 'book',
    }))
  }, [])

  const handleSelectRestaurant = useCallback((restaurant: Restaurant) => {
    setPrefill(`I would like to make a reservation at ${restaurant.name}.`)
    setBookView('chat')
    setAppState((prev) => ({
      ...prev,
      bookingFields: { ...prev.bookingFields, restaurant: restaurant.name },
      screen: 'book',
    }))
  }, [])

  const handleNewReservation = useCallback(() => {
    sessionIdRef.current = resetSession()
    hasSentMessageRef.current = false
    setPrefill(undefined)
    setBookView('chat')
    setAppState(makeBase())
  }, [])

  const handleBookRestaurant = useCallback((restaurant: Restaurant) => {
    setPrefill(`I would like to make a reservation at ${restaurant.name}.`)
    setBookView('chat')
    setAppState((prev) => ({
      ...prev,
      screen: 'book',
      bookingFields: { ...prev.bookingFields, restaurant: restaurant.name },
    }))
  }, [])

  const canOpenConfirmed = appState.confirmationCode !== null
  const showConfirmed = appState.screen === 'book' && bookView === 'confirmed' && canOpenConfirmed
  const activeView: 'browse' | 'chat' | 'confirmed' =
    appState.screen === 'browse'
      ? 'browse'
      : showConfirmed
        ? 'confirmed'
        : 'chat'

  return (
    <>
      <Navbar
        onHome={handleHome}
        onBrowse={handleBrowse}
        onChat={handleChatView}
        onConfirmed={handleConfirmedView}
        activeView={activeView}
        canOpenConfirmed={canOpenConfirmed}
      />

      <main style={{ paddingTop: '60px', minHeight: '100vh' }}>
        {appState.screen === 'browse' ? (
          <BrowseScreen onBookRestaurant={handleBookRestaurant} defaultOpenId={null} />
        ) : showConfirmed ? (
          <div className="flex" style={{ minHeight: 'calc(100vh - 60px)' }}>
            <ConfirmedLeftColumn
              confirmationCode={appState.confirmationCode!}
              bookingFields={appState.bookingFields}
              onNewReservation={handleNewReservation}
            />
            <ConfirmedRightPanel bookingFields={appState.bookingFields} />
          </div>
        ) : (
          <div className="flex" style={{ minHeight: 'calc(100vh - 60px)' }}>
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
            <ContextPanel
              state={appState}
              onCheckAvailability={handleCheckAvailability}
              onSelectRestaurant={handleSelectRestaurant}
            />
          </div>
        )}
      </main>
    </>
  )
}
