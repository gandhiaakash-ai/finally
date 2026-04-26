/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV === "development";
const backend = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  // Static export for production (consumed by FastAPI from "/").
  ...(isDev ? {} : { output: "export" }),
  reactStrictMode: true,
  trailingSlash: false,
  images: {
    unoptimized: true,
  },
  // In dev, proxy /api/* to the FastAPI backend so the frontend runs on :3000
  // and still sees same-origin endpoints. Production is served by FastAPI itself.
  async rewrites() {
    if (!isDev) return [];
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

module.exports = nextConfig;
