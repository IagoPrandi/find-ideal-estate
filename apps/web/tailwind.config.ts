import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        panel: "var(--color-panel)",
        border: "var(--color-border)",
        text: "var(--color-text)",
        muted: "var(--color-muted)",
        primary: "var(--color-primary)",
        success: "var(--color-success)",
        warning: "var(--color-warning)",
        danger: "var(--color-danger)",
        "pastel-violet": {
          50: "#f3f0ff",
          100: "#e5dbff",
          200: "#d0bfff",
          300: "#b197fc",
          400: "#9775fa",
          500: "#845ef7",
          600: "#7048e8",
          700: "#6741d9",
          800: "#5f3dc4"
        }
      },
      boxShadow: {
        panel: "var(--shadow-panel)"
      },
      borderRadius: {
        panel: "var(--radius-panel)"
      },
      spacing: {
        3: "0.75rem",
        4: "1rem",
        6: "1.5rem"
      }
    }
  },
  plugins: []
};

export default config;