import { readFileSync } from "fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const { version } = JSON.parse(readFileSync("./package.json", "utf-8")) as {
  version: string;
};

export default defineConfig({
  define: {
    __UI_VERSION__: JSON.stringify(version),
  },
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:5000", changeOrigin: true },
      "/health": { target: "http://localhost:5000", changeOrigin: true },
    },
  },
});
