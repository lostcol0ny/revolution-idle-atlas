import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Serve and build from the repo-root public/ directory directly. There is no
  // copy step, so the app can never render a stale graph.json.
  publicDir: '../public',
  base: '/',
  server: {
    // publicDir sits outside the Vite root, so the dev server needs explicit
    // permission to read the parent directory.
    fs: { allow: ['..'] },
  },
  test: {
    environment: 'node',
    // tsconfig.node.json already typechecks .test.tsx. Matching it here means a
    // future component test cannot land typechecked but silently never run.
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
