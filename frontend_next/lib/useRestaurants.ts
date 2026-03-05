'use client'
import { useState, useEffect } from 'react'
import type { Restaurant } from './types'
import { fetchRestaurants } from './api'
import { RESTAURANTS as MOCK_RESTAURANTS } from './mock-data'

export function useRestaurants() {
    const [restaurants, setRestaurants] = useState<Restaurant[]>(
        MOCK_RESTAURANTS // start with mock, replace with real
    )
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        fetchRestaurants()
            .then((data) => {
                if (data.length > 0) {
                    setRestaurants(data)
                }
                setLoading(false)
            })
            .catch((err) => {
                setError(err.message)
                setLoading(false)
                // Keep showing mock data on error
            })
    }, [])

    return { restaurants, loading, error }
}
