import type { Config } from "tailwindcss";
import tailwindAnimate from "tailwindcss-animate";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Space Grotesk", "IBM Plex Sans", "sans-serif"],
        body: ["IBM Plex Sans", "Segoe UI", "sans-serif"],
      },
      colors: {
        // #1847 / #1841: brand tokens resolve to the `--ss-*` CSS custom
        // properties (RGB channels in index.css) so opacity modifiers work and
        // the palette has a single source of truth. Full-opacity values are the
        // exact original hexes (canvas #f5f1e8, ink #1c211b, ember #f06a44,
        // pine #2e5d50, sea #2d7891, sand #ddc49d).
        canvas: "rgb(var(--ss-canvas) / <alpha-value>)",
        ink: "rgb(var(--ss-ink) / <alpha-value>)",
        ember: "rgb(var(--ss-ember) / <alpha-value>)",
        pine: "rgb(var(--ss-pine) / <alpha-value>)",
        sea: "rgb(var(--ss-sea) / <alpha-value>)",
        sand: "rgb(var(--ss-sand) / <alpha-value>)",
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        panel: "0 18px 48px rgba(20, 26, 24, 0.12)",
      },
    },
  },
  plugins: [tailwindAnimate],
} satisfies Config;
