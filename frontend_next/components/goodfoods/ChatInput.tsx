'use client'

import { useState, useRef, useEffect } from 'react'
import { ArrowUp } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string) => void
  prefill?: string
}

export function ChatInput({ onSend, prefill }: ChatInputProps) {
  const [value, setValue] = useState('')
  const [focused, setFocused] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  /* Apply prefill when it changes */
  useEffect(() => {
    if (prefill) {
      setValue(prefill)
      textareaRef.current?.focus()
    }
  }, [prefill])

  /* Auto-resize */
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 140) + 'px'
  }, [value])

  const hasContent = value.trim().length > 0

  function handleSend() {
    const trimmed = value.trim()
    if (!trimmed) return
    onSend(trimmed)
    setValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div
      className="sticky bottom-0"
      style={{
        background: 'linear-gradient(to top, #080808 70%, transparent)',
        padding: '20px 0 32px 0',
      }}
    >
      {/* Input container */}
      <div
        className="relative"
        style={{
          background: '#111111',
          border: `1px solid ${focused ? '#c9a96e' : '#2d2d2d'}`,
          borderRadius: '14px',
          padding: '16px 56px 16px 20px',
          boxShadow: focused
            ? '0 0 0 1px rgba(201,169,110,0.1)'
            : 'none',
          transition: 'border-color 150ms, box-shadow 150ms',
        }}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="Describe what you're looking for..."
          rows={1}
          aria-label="Tell Sage what you're looking for"
          className="w-full resize-none outline-none"
          style={{
            background: 'transparent',
            border: 'none',
            fontSize: '14px',
            color: '#f7f3ee',
            lineHeight: 1.6,
            minHeight: '24px',
            maxHeight: '140px',
            fontFamily: 'inherit',
          }}
        />

        {/* Send button — absolute bottom-right */}
        <button
          onClick={handleSend}
          disabled={!hasContent}
          aria-label="Send message"
          className="absolute flex items-center justify-center transition-colors duration-150"
          style={{
            right: '14px',
            bottom: '14px',
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            background: hasContent ? '#c9a96e' : '#222222',
            border: 'none',
            cursor: hasContent ? 'pointer' : 'default',
          }}
          onMouseEnter={(e) => {
            if (hasContent) e.currentTarget.style.background = '#e8cc9a'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = hasContent ? '#c9a96e' : '#222222'
          }}
        >
          <ArrowUp
            size={15}
            style={{ color: hasContent ? '#080808' : '#504a44' }}
          />
        </button>
      </div>

      {/* Tagline */}
      <p
        className="text-center mt-3"
        style={{ fontSize: '11px', color: '#504a44' }}
      >
        Sage is here to help &middot; GoodFoods &middot; 75 Locations
      </p>
    </div>
  )
}
