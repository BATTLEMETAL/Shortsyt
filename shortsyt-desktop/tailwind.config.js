/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        lol: {
          bg: '#0A0E1A',
          bgDark: '#070A12',
          bgCard: '#121624',
          bgElevated: '#1A1E30',
          bgInput: '#1E2338',
          gold: '#C89B3C',
          goldLight: '#E5C269',
          goldDim: '#7A6026',
          text: '#E4D6B5',
          textMuted: '#8B8FA8',
          textDark: '#50546A',
          blue: '#2A7FD4',
          blueLight: '#4FA3F7',
          blueDim: '#1B4D82',
          red: '#E84040',
          redLight: '#FF6060',
          green: '#2ECC71',
          greenLight: '#55E88D',
          border: '#1E2438',
          borderLight: '#2D3550',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        impact: ['Impact', 'sans-serif'],
      }
    },
  },
  plugins: [],
};
