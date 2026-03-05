'use client'

import type { Message } from '@/lib/types'

/* Strip any markdown that might come from the AI layer */
function stripMarkdown(text: string): string {
  return text
    .replace(/#{1,6}\s+/g, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/`(.*?)`/g, '$1')
    .replace(/^[-*+]\s/gm, '')
}

/* Sage's "S" avatar — 36px circle with Cormorant Garamond italic gold S */
function SageAvatar({ size = 36 }: { size?: number }) {
  return (
    <div
      aria-hidden="true"
      className="flex-shrink-0 flex items-center justify-center"
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        background: 'linear-gradient(135deg, #1e1a0f, #2a2010)',
        border: '1px solid #3a2e18',
      }}
    >
      <span
        className="font-serif italic leading-none"
        style={{ fontSize: size * 0.44, color: '#c9a96e' }}
      >
        S
      </span>
    </div>
  )
}

/* Sage composing — 3-dot typing indicator */
export function SageComposing() {
  return (
    <div className="flex items-center gap-2.5 msg-appear" role="status" aria-label="Sage is composing">
      <SageAvatar size={28} />
      <div className="flex items-center gap-1" style={{ padding: '8px 4px' }}>
        <span className="sage-dot" />
        <span className="sage-dot" />
        <span className="sage-dot" />
      </div>
    </div>
  )
}

/* Guest message — right-aligned */
function GuestMessage({ content }: { content: string }) {
  return (
    <div className="flex flex-col items-end gap-1 msg-appear">
      <span style={{ fontSize: '11px', color: '#504a44' }}>You</span>
      <div
        style={{
          background: '#1c1c1c',
          border: '1px solid #2d2d2d',
          borderRadius: '14px 14px 3px 14px',
          padding: '13px 17px',
          maxWidth: '78%',
          fontSize: '14px',
          color: '#f7f3ee',
          lineHeight: 1.6,
        }}
      >
        {content}
      </div>
    </div>
  )
}

/* Sage message — left-aligned with avatar */
function SageMessage({ content }: { content: string }) {
  const clean = stripMarkdown(content)
  const paragraphs = clean.split(/\n+/).filter(Boolean)

  return (
    <div className="flex items-start gap-2.5 msg-appear">
      <SageAvatar size={36} />
      <div className="flex flex-col gap-1" style={{ maxWidth: '84%' }}>
        <span style={{ fontSize: '11px', color: '#c9a96e' }}>Sage</span>
        <div
          style={{
            background: '#111111',
            border: '1px solid #1e1e1e',
            borderRadius: '3px 14px 14px 14px',
            padding: '14px 18px',
            fontSize: '14px',
            color: '#f7f3ee',
            lineHeight: 1.7,
          }}
        >
          {paragraphs.map((p, i) => (
            <p key={i} style={{ margin: i > 0 ? '10px 0 0 0' : 0 }}>
              {p}
            </p>
          ))}
        </div>
      </div>
    </div>
  )
}

export function ChatMessage({ message }: { message: Message }) {
  if (message.role === 'composing') return <SageComposing />
  if (message.role === 'user') return <GuestMessage content={message.content} />
  return <SageMessage content={message.content} />
}
