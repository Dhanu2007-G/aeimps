/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        brand: { 50:'#f0f4ff', 500:'#4f6ef7', 600:'#3b5bdb', 700:'#2f4ac7' },
      },
    },
  },
  plugins: [],
};
