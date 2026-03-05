export type BookingState =
  | 'GREETING'
  | 'SEARCHING'
  | 'PRESENTING_OPTIONS'
  | 'CONFIRMING_DETAILS'
  | 'COMPLETED'

export type Screen = 'book' | 'browse'

/** UIState: 1=Landing 2=Conversation 3=Confirmed 4=Browse */
export type UIState = 1 | 2 | 3 | 4

export interface Restaurant {
  id: string
  name: string
  neighborhood: string
  cuisine_type: string
  price_range: number
  total_capacity: number
  dietary_certifications: string[]
  ambiance_tags: string[]
  operating_hours: { open: string; close: string }
  description: string
}

export interface Message {
  id: string
  /** 'user' = guest, 'sage' = concierge, 'composing' = Sage typing indicator */
  role: 'user' | 'sage' | 'composing'
  content: string
}

export interface BookingFields {
  restaurant: string | null
  partySize: string | null
  date: string | null
  time: string | null
  occasion: string | null
}

export interface AppState {
  screen: Screen
  bookingState: BookingState
  messages: Message[]
  bookingFields: BookingFields
  searchResults: Restaurant[]
  confirmationCode: string | null
}
