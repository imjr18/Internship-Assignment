'use client'

interface NavbarProps {
  onNavigate: (screen: 'book' | 'browse') => void
}

const NAV_LINKS = [
  { label: 'Our Restaurants', screen: 'browse' as const },
  { label: 'Private Dining',  screen: 'book'   as const },
  { label: 'Gift Cards',      screen: 'book'   as const },
]

export function Navbar({ onNavigate }: NavbarProps) {
  return (
    <header
      className="fixed top-0 left-0 right-0 z-[100] flex items-center justify-between px-8"
      style={{
        height: '60px',
        background: '#080808',
        borderBottom: '1px solid #1a1a1a',
      }}
    >
      {/* Wordmark */}
      <button
        onClick={() => onNavigate('book')}
        className="font-serif italic leading-none cursor-pointer"
        style={{
          fontSize: '26px',
          color: '#c9a96e',
          letterSpacing: '-0.01em',
          background: 'none',
          border: 'none',
          padding: 0,
        }}
        aria-label="GoodFoods — go to home"
      >
        GoodFoods
      </button>

      {/* Center nav links — desktop only */}
      <nav
        className="hidden md:flex items-center"
        style={{ gap: '32px' }}
        aria-label="Main navigation"
      >
        {NAV_LINKS.map((link) => (
          <button
            key={link.label}
            onClick={() => onNavigate(link.screen)}
            className="transition-colors duration-150 cursor-pointer"
            style={{
              fontSize: '13px',
              color: '#a09a92',
              background: 'none',
              border: 'none',
              padding: 0,
              fontFamily: 'inherit',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = '#f7f3ee')}
            onMouseLeave={(e) => (e.currentTarget.style.color = '#a09a92')}
          >
            {link.label}
          </button>
        ))}
      </nav>

      {/* Find a Table pill */}
      <button
        onClick={() => onNavigate('book')}
        className="transition-colors duration-150 cursor-pointer"
        style={{
          height: '34px',
          padding: '0 18px',
          background: '#c9a96e',
          color: '#080808',
          borderRadius: '100px',
          fontSize: '13px',
          fontWeight: 500,
          border: 'none',
          fontFamily: 'inherit',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = '#e8cc9a')}
        onMouseLeave={(e) => (e.currentTarget.style.background = '#c9a96e')}
      >
        Find a Table
      </button>
    </header>
  )
}
