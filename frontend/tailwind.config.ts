import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Class Trader dark palette
        bg: '#0A0E17',
        surface: '#111827',
        'surface-2': '#1a2235',
        border: '#1f2d44',
        'text-primary': '#E5E7EB',
        'text-secondary': '#9CA3AF',
        'text-muted': '#6B7280',
        // Semantic colors
        gain: '#10B981',
        loss: '#EF4444',
        warning: '#F59E0B',
        info: '#3B82F6',
        // Accent aliases
        green: '#10B981',
        red: '#EF4444',
        amber: '#F59E0B',
        blue: '#3B82F6',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'IBM Plex Mono', 'Fira Code', 'monospace'],
        sans: ['DM Sans', 'Manrope', 'Inter', 'system-ui', 'sans-serif'],
      },
      backgroundImage: {
        'gradient-surface': 'linear-gradient(135deg, #111827 0%, #0f1a2e 100%)',
      },
    },
  },
  plugins: [],
} satisfies Config
