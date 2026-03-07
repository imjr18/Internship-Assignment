'use client'

interface NavbarProps {
  onHome: () => void
  onBrowse: () => void
  onChat: () => void
  onConfirmed: () => void
  activeView: 'browse' | 'chat' | 'confirmed'
  canOpenConfirmed: boolean
}

function NavButton({
  label,
  active,
  disabled = false,
  onClick,
}: {
  label: string
  active: boolean
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="transition-colors duration-150"
      style={{
        fontSize: '13px',
        color: active ? '#f7f3ee' : '#a09a92',
        background: 'none',
        border: 'none',
        padding: 0,
        fontFamily: 'inherit',
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.4 : 1,
      }}
      onMouseEnter={(e) => {
        if (!disabled && !active) e.currentTarget.style.color = '#f7f3ee'
      }}
      onMouseLeave={(e) => {
        if (!disabled && !active) e.currentTarget.style.color = '#a09a92'
      }}
      aria-label={label}
    >
      {label}
    </button>
  )
}

export function Navbar({
  onHome,
  onBrowse,
  onChat,
  onConfirmed,
  activeView,
  canOpenConfirmed,
}: NavbarProps) {
  return (
    <header
      className="fixed top-0 left-0 right-0 z-[100] flex items-center justify-between px-8"
      style={{
        height: '60px',
        background: '#080808',
        borderBottom: '1px solid #1a1a1a',
      }}
    >
      <button
        onClick={onHome}
        className="font-serif italic leading-none cursor-pointer"
        style={{
          fontSize: '26px',
          color: '#c9a96e',
          letterSpacing: '-0.01em',
          background: 'none',
          border: 'none',
          padding: 0,
        }}
        aria-label="GoodFoods - go to home"
      >
        GoodFoods
      </button>

      <nav
        className="flex items-center"
        style={{ gap: '24px' }}
        aria-label="Main navigation"
      >
        <NavButton
          label="Our Restaurants"
          active={activeView === 'browse'}
          onClick={onBrowse}
        />
        <NavButton
          label="Chat"
          active={activeView === 'chat'}
          onClick={onChat}
        />
        <NavButton
          label="Confirmed"
          active={activeView === 'confirmed'}
          disabled={!canOpenConfirmed}
          onClick={onConfirmed}
        />
      </nav>

      <div style={{ width: '92px' }} />
    </header>
  )
}
