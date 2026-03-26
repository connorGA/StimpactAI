type BrandMarkProps = {
  className?: string;
};

export function BrandMark({ className = "h-10 w-10" }: BrandMarkProps) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 64 64"
      className={`brand-mark-shell ${className}`}
      fill="none"
    >
      <defs>
        <linearGradient id="brandHexStroke" x1="9" y1="34" x2="55" y2="30" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#4b6bfb" />
          <stop offset="52%" stopColor="#69c7ff" />
          <stop offset="74%" stopColor="#ff6a3d" />
          <stop offset="100%" stopColor="#ffb253" />
          <animateTransform
            attributeName="gradientTransform"
            type="rotate"
            from="0 32 32"
            to="360 32 32"
            dur="9s"
            repeatCount="indefinite"
          />
        </linearGradient>
        <linearGradient id="brandCrossFill" x1="22" y1="20" x2="42" y2="44" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#f8fdff" />
          <stop offset="45%" stopColor="#d8f3ff" />
          <stop offset="100%" stopColor="#fff3ec" />
        </linearGradient>
        <linearGradient id="brandEnergyStroke" x1="12" y1="18" x2="52" y2="46" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#72d2ff" />
          <stop offset="55%" stopColor="#4b6bfb" />
          <stop offset="100%" stopColor="#ff8c69" />
          <animateTransform
            attributeName="gradientTransform"
            type="translate"
            values="-18 0;18 0;-18 0"
            dur="4.6s"
            repeatCount="indefinite"
          />
        </linearGradient>
        <filter id="brandGlow" x="-40%" y="-40%" width="180%" height="180%">
          <feDropShadow dx="0" dy="0" stdDeviation="2.2" floodColor="#4b6bfb" floodOpacity="0.8" />
          <feDropShadow dx="0" dy="0" stdDeviation="2.2" floodColor="#ff6a3d" floodOpacity="0.42" />
        </filter>
      </defs>

      <g filter="url(#brandGlow)">
        <path
          d="M32 6 53.65 18.5v25L32 56 10.35 43.5v-25L32 6Z"
          className="brand-mark-outline"
          stroke="url(#brandHexStroke)"
          strokeWidth="3"
          strokeLinejoin="round"
        />
        <path
          d="M32 12.5 48 21.7v18.6L32 49.5 16 40.3V21.7L32 12.5Z"
          className="brand-mark-inner-outline"
          stroke="url(#brandHexStroke)"
          strokeWidth="1.8"
          strokeLinejoin="round"
          opacity="0.9"
        />
        <path
          d="M20 25h9v-9h6v9h9v6h-9v9h-6v-9h-9z"
          className="brand-mark-cross"
          fill="url(#brandCrossFill)"
          stroke="rgba(109, 213, 255, 0.85)"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
      </g>

      <g className="brand-mark-circuit-group">
        <path
          d="M16 32h9"
          className="brand-mark-circuit"
          stroke="url(#brandEnergyStroke)"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
        <path
          d="M39 32h9"
          className="brand-mark-circuit"
          stroke="url(#brandEnergyStroke)"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
        <path
          d="M32 16v9"
          className="brand-mark-circuit"
          stroke="url(#brandEnergyStroke)"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
        <path
          d="M32 39v9"
          className="brand-mark-circuit"
          stroke="url(#brandEnergyStroke)"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
        <path
          d="M18 24h6v-4h5"
          className="brand-mark-trace"
          stroke="url(#brandEnergyStroke)"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M46 24h-6v-4h-5"
          className="brand-mark-trace"
          stroke="url(#brandEnergyStroke)"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M18 40h6v4h5"
          className="brand-mark-trace"
          stroke="url(#brandEnergyStroke)"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M46 40h-6v4h-5"
          className="brand-mark-trace"
          stroke="url(#brandEnergyStroke)"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>

      <g className="brand-mark-nodes">
        <circle cx="18" cy="24" r="1.7" className="brand-mark-node brand-mark-node-blue" />
        <circle cx="46" cy="24" r="1.7" className="brand-mark-node brand-mark-node-orange" />
        <circle cx="18" cy="40" r="1.7" className="brand-mark-node brand-mark-node-blue" />
        <circle cx="46" cy="40" r="1.7" className="brand-mark-node brand-mark-node-orange" />
        <circle cx="32" cy="16" r="1.5" className="brand-mark-node brand-mark-node-blue" />
        <circle cx="32" cy="48" r="1.5" className="brand-mark-node brand-mark-node-orange" />
      </g>
    </svg>
  );
}
