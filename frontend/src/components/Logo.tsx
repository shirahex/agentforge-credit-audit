/** Mark: a risk curve that falls under the refusal threshold. */
export function Logo({ size = 24, inverted = false }: { size?: number; inverted?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <rect width="24" height="24" rx="6.5" fill={inverted ? '#ffffff' : 'var(--color-ink)'} />
      <line x1="5" x2="19" y1="13.5" y2="13.5" stroke={inverted ? '#0a0f1c' : 'var(--color-canvas)'} strokeOpacity="0.35" strokeWidth="1.2" strokeDasharray="1.6 1.6" />
      <path d="M5 7.5 C 9 7.5, 10 9, 12 12 S 15.5 17, 19 17" fill="none" stroke="#5b78ff" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="19" cy="17" r="1.9" fill="#5b78ff" />
    </svg>
  )
}
