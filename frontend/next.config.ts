import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle, so the Docker image runs with `node server.js`.
  output: "standalone",
  poweredByHeader: false,
  // Stop `next dev` from writing an AGENTS.md file into this folder.
  agentRules: false,
};

export default nextConfig;
