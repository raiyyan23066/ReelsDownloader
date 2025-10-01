/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/**/*.js"
  ],
  theme: {
    extend: {
      animation: {
        'spin': 'spin 1s linear infinite',
      }
    },
  },
  plugins: [],
}
