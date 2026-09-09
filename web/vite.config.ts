import { defineConfig } from 'vite';

export default defineConfig({
  base: '/adopt-hokkaido-lidar/',
  build: {
    outDir: '../docs',
    emptyOutDir: true
  }
});
