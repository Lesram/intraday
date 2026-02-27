/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { visualizer } from 'rollup-plugin-visualizer'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Generate bundle analysis report on build
    visualizer({
      filename: 'dist/bundle-analysis.html',
      open: false,
      gzipSize: true,
      brotliSize: true,
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@components': path.resolve(__dirname, './src/components'),
      '@features': path.resolve(__dirname, './src/features'),
      '@hooks': path.resolve(__dirname, './src/hooks'),
      '@services': path.resolve(__dirname, './src/services'),
      '@store': path.resolve(__dirname, './src/store'),
      '@utils': path.resolve(__dirname, './src/utils'),
      '@types': path.resolve(__dirname, './src/types'),
      '@styles': path.resolve(__dirname, './src/styles'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true, // Enable WebSocket proxying for /api/v1/market-data/ws
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/socket.io': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    // Optimize chunk sizes for production
    chunkSizeWarningLimit: 500, // Warn for chunks over 500kb
    // Use esbuild for minification (faster than terser, built into Vite)
    minify: 'esbuild',
    // Target modern browsers only (smaller output)
    target: 'esnext',
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          // More granular chunking for better tree-shaking
          if (id.includes('node_modules')) {
            // Core React dependencies - small, cached forever
            if (id.includes('react-dom') || id.includes('/react/')) {
              return 'vendor-react';
            }
            if (id.includes('react-router')) {
              return 'vendor-router';
            }
            // Ant Design - split into core and icons
            if (id.includes('@ant-design/icons')) {
              return 'antd-icons';
            }
            if (id.includes('antd')) {
              return 'antd';
            }
            // Charting libraries - split by library
            if (id.includes('lightweight-charts')) {
              return 'charts-lightweight';
            }
            if (id.includes('chart.js') || id.includes('react-chartjs')) {
              return 'charts-chartjs';
            }
            if (id.includes('recharts')) {
              return 'charts-recharts';
            }
            // AG-Grid (very large, lazy load recommended)
            if (id.includes('ag-grid')) {
              return 'grid';
            }
            // State management
            if (id.includes('@tanstack/react-query')) {
              return 'state-query';
            }
            if (id.includes('zustand')) {
              return 'state-zustand';
            }
            // HTTP/WebSocket
            if (id.includes('axios')) {
              return 'network-axios';
            }
            if (id.includes('socket.io')) {
              return 'network-socketio';
            }
            // Form handling
            if (id.includes('react-hook-form') || id.includes('@hookform')) {
              return 'forms';
            }
            // Date utilities
            if (id.includes('date-fns')) {
              return 'utils-date';
            }
            // DnD
            if (id.includes('@dnd-kit')) {
              return 'dnd';
            }
            // Mermaid (large diagram library)
            if (id.includes('mermaid')) {
              return 'mermaid';
            }
            // Validation
            if (id.includes('zod')) {
              return 'validation';
            }
            // All other dependencies
            return 'vendor-other';
          }
        },
        // Use hashed chunk names for better caching
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
      // Tree-shake more aggressively
      treeshake: {
        moduleSideEffects: 'no-external',
        propertyReadSideEffects: false,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      exclude: [
        'node_modules/',
        'src/test/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/mockData/',
        'dist/',
      ],
    },
  },
})
