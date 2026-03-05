/**
 * Gets or creates a stable session ID for this
 * browser session. Stored in sessionStorage so
 * it resets when the tab is closed.
 */
export function getSessionId(): string {
    if (typeof window === 'undefined') return 'ssr'

    const key = 'gf_session_id'
    let id = sessionStorage.getItem(key)
    if (!id) {
        id = `web-${Date.now()}-${Math.random()
            .toString(36)
            .slice(2, 8)}`
        sessionStorage.setItem(key, id)
    }
    return id
}

export function resetSession(): string {
    if (typeof window === 'undefined') return 'ssr'
    const key = 'gf_session_id'
    const id = `web-${Date.now()}-${Math.random()
        .toString(36)
        .slice(2, 8)}`
    sessionStorage.setItem(key, id)
    return id
}
