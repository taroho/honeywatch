/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // HoneyWatch カスタムカラー
        hw: {
          bg: "#0f172a",
          card: "#1e293b",
          border: "#334155",
          accent: "#3b82f6",
          ssh: "#f59e0b",
          http: "#10b981",
          danger: "#ef4444",
        },
      },
    },
  },
  plugins: [],
};
