const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8100'

export type ChatToken =
    | { type: 'text'; content: string }
    | { type: 'tool'; name: string }
    | { type: 'booking'; data: Record<string, unknown> }
    | { type: 'escalated' }
    | { type: 'done' }
    | { type: 'error'; message: string }

/**
 * Streams a chat message to the Python agent.
 * Parses the special tokens the orchestrator emits.
 * Calls onToken for each parsed event.
 */
export async function streamChat(
    sessionId: string,
    message: string,
    onToken: (token: ChatToken) => void
): Promise<void> {
    const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            message,
        }),
    })

    if (!response.ok) {
        onToken({ type: 'error', message: `HTTP ${response.status}` })
        return
    }

    const reader = response.body?.getReader()
    if (!reader) {
        onToken({ type: 'error', message: 'No response body' })
        return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6).trim()
            if (raw === '[DONE]') {
                onToken({ type: 'done' })
                return
            }

            let parsed: { token?: string; error?: string }
            try {
                parsed = JSON.parse(raw)
            } catch {
                continue
            }

            if (parsed.error) {
                onToken({ type: 'error', message: parsed.error })
                continue
            }

            const token = parsed.token ?? ''
            if (!token) continue

            // Parse special tokens from orchestrator
            if (token.startsWith('[TOOL_START:')) {
                const name = token.slice(12, -1)
                onToken({ type: 'tool', name })
            } else if (token.startsWith('[TOOL_END:')) {
                // tool finished — no UI action needed
            } else if (token.startsWith('[BOOKING_COMPLETE:')) {
                try {
                    const jsonStr = token.slice(18, -1)
                    const data = JSON.parse(jsonStr)
                    onToken({ type: 'booking', data })
                } catch {
                    // malformed payload, ignore
                }
            } else if (token === '[ESCALATED]') {
                onToken({ type: 'escalated' })
            } else {
                onToken({ type: 'text', content: token })
            }
        }
    }
}

/**
 * Fetch booking state for a session.
 * Returns null on any error.
 */
export async function fetchBookingState(
    sessionId: string
): Promise<Record<string, unknown> | null> {
    try {
        const res = await fetch(
            `${API_BASE}/booking-state/${sessionId}`
        )
        if (!res.ok) return null
        return res.json()
    } catch {
        return null
    }
}

/**
 * Fetch all restaurants from the real database.
 * Returns empty array on error.
 */
export async function fetchRestaurants(): Promise<
    import('./types').Restaurant[]
> {
    try {
        const res = await fetch(`${API_BASE}/restaurants`)
        if (!res.ok) return []
        return res.json()
    } catch {
        return []
    }
}
