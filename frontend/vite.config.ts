import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// mode "demo" : un seul fichier HTML autonome, API simulée en mémoire (aucun appel réseau).
export default defineConfig(({ mode }) => ({
  plugins: mode === "demo" ? [react(), viteSingleFile()] : [react()],
  define: { __DEMO__: JSON.stringify(mode === "demo") },
  build: mode === "demo" ? { outDir: "dist-demo", assetsInlineLimit: 100_000_000 } : { outDir: "dist" },
  server: {
    proxy: { "/api": "http://localhost:8000", "/webhooks": "http://localhost:8000" },
  },
}));
