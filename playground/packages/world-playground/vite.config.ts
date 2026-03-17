import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  base: '/agent-hypervisor/',
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
  },
});
