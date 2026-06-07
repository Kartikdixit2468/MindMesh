import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        monad: {
          purple: "#6366f1",
          blue: "#3b82f6",
          cyan: "#06b6d4",
          green: "#10b981",
          dark: "#0a0a1a",
          card: "#111827",
          border: "#1f2937",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        glow: "glow 2s ease-in-out infinite alternate",
      },
      keyframes: {
        glow: {
          from: { boxShadow: "0 0 5px #6366f1, 0 0 10px #6366f1" },
          to: { boxShadow: "0 0 20px #6366f1, 0 0 40px #6366f1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
