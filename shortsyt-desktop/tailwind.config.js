/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        fk: {
          k0: '#050505',
          k1: '#0E0F11',
          k2: '#17191C',
          k3: '#272A2F',
          volt: '#C8FF3A',
          voltD: '#AEE820',
          white: '#FFFFFF',
          bone: '#FFFFFF',
          pl: '#EEF0EB',
          mut: '#A0A7B1',
          dim: '#686E78',
          ink: '#050505',
        },
        lol: {
          bg: '#050505',
          card: '#0E0F11',
          elevated: '#17191C',
          gold: '#C8FF3A',
          goldHover: '#AEE820',
          blue: '#5CAEFF',
          text: '#FFFFFF',
          textSecondary: '#A0A7B1',
          border: '#272A2F',
        },
      },
      fontFamily: {
        sans: ['"Manrope"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
