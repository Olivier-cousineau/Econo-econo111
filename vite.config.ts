import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  build: {
    outDir: resolve(__dirname, 'public/assets/js'),
    emptyOutDir: false,
    sourcemap: false,
    rollupOptions: {
      input: resolve(__dirname, 'src/js/main.ts'),
      output: {
        entryFileNames: 'main.js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'chunks/[name]-[hash][extname]',
      },
    },
  },
});
