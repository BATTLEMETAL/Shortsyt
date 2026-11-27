import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: './',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (id.includes('lucide-react')) return 'vendor-icons';
          if (id.includes('axios')) return 'vendor-axios';
          if (
            id.includes('react-router') ||
            id.includes('react-dom') ||
            /[\\/]react[\\/]/.test(id)
          ) {
            return 'vendor-react';
          }
        },
      },
    },
  },
});
