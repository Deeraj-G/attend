// Small inline icons; stroke uses currentColor so they follow the text colour.

type IconProps = { size?: number }

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
})

export function PulseIcon({ size = 18 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="M3 12h4l2.5-5 4 10 2.5-5H21" />
    </svg>
  )
}

export function MicIcon({ size = 18 }: IconProps) {
  return (
    <svg {...base(size)}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
    </svg>
  )
}

export function StopIcon({ size = 18 }: IconProps) {
  return (
    <svg {...base(size)}>
      <rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function CheckIcon({ size = 16 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </svg>
  )
}

export function ShieldIcon({ size = 22 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.2 7.5 9.5 4.3-1.3 7.5-4.9 7.5-9.5V6L12 3Z" />
      <path d="m8.8 12 2.2 2.2 4.2-4.4" />
    </svg>
  )
}

export function DocIcon({ size = 22 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M9 11h6M9 14.5h6M9 18h3.5" />
    </svg>
  )
}

export function LockIcon({ size = 22 }: IconProps) {
  return (
    <svg {...base(size)}>
      <rect x="5" y="10.5" width="14" height="10" rx="2" />
      <path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3" />
    </svg>
  )
}

export function PlayIcon({ size = 14 }: IconProps) {
  return (
    <svg {...base(size)}>
      <path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function Target({ color, size = 72 }: { color: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 72 72" fill="none" stroke={color} aria-hidden="true">
      <circle cx="36" cy="36" r="27" strokeWidth="2" />
      <circle cx="36" cy="36" r="13" strokeWidth="2" />
      <circle cx="36" cy="36" r="3.5" fill={color} stroke="none" />
      <path d="M36 2v20M36 50v20M2 36h20M50 36h20" strokeWidth="1.5" strokeDasharray="3 3" />
    </svg>
  )
}
