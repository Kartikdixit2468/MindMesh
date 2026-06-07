/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_ORCHESTRATOR_URL: process.env.NEXT_PUBLIC_ORCHESTRATOR_URL || "http://localhost:8000",
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws",
    NEXT_PUBLIC_MONAD_CHAIN_ID: process.env.NEXT_PUBLIC_MONAD_CHAIN_ID || "10143",
  },
};

module.exports = nextConfig;
