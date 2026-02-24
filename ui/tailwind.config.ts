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
        danger: "var(--color-danger)"
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