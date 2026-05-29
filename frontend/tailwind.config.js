/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        mint: {
          100: "#E4FDF6",
          200: "#CAFBED",
          400: "#4FF5C3",
        },
      },
    },
  },
  plugins: [],
}