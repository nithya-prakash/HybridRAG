/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // "standalone" output is for infra/docker/frontend.Dockerfile's
  // self-contained Docker build (docker-compose.prod.yml's target — it
  // COPYs .next/standalone directly into the runtime image). Vercel's own
  // build pipeline has its own equivalent packaging step and breaks on this
  // setting (looks for a .../next-server.js.nft.json trace file that
  // standalone mode relocates, ENOENT). `VERCEL` is set automatically by
  // Vercel's build environment — nowhere else — so this stays "standalone"
  // for the Docker build and unset everywhere Vercel builds it.
  output: process.env.VERCEL ? undefined : "standalone",
};

export default nextConfig;
