/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'deep-navy': '#071827',
        panel: '#0E263A',
        'panel-soft': '#14324A',
        'grid-blue': '#1E88E5',
        'electric-cyan': '#18D4FF',
        'risk-amber': '#FFB020',
        'critical-red': '#E5484D',
        'vegetation-green': '#2FB344',
        'substation-violet': '#7C3AED',
        sandstone: '#D8B06A',
        'text-primary': '#F5FAFF',
        'text-secondary': '#A9BED1',
        border: '#254963',
      },
      fontFamily: {
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: ['JetBrains Mono', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        panel: '0 8px 32px rgba(0, 0, 0, 0.45)',
        card: '0 4px 18px rgba(0, 0, 0, 0.30)',
        glow: '0 0 24px rgba(24, 212, 255, 0.18)',
      },
    },
  },
  plugins: [],
};
