import { defineConfig } from 'vite';

export default defineConfig({
  base: '/adopt-hokkaido-lidar/',
  worker: {
    rolldownOptions: {
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js'
      }
    }
  },
  build: {
    outDir: '../docs',
    emptyOutDir: true,
    // No content-hash suffixes on output filenames: this is a small,
    // infrequently-changing site with no CDN cache-busting need, and the
    // hashed names were the direct cause of the "browser shows an old JS
    // bundle" confusion earlier in this project's history.
    rolldownOptions: {
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]'
      }
    }
  }
});
