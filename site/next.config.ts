import type { NextConfig } from "next";

const distDir = process.env.NEXT_DIST_DIR?.trim();
const useStandaloneOutput = process.env.NEXT_OUTPUT === "standalone";

const nextConfig: NextConfig = {
  ...(useStandaloneOutput ? { output: "standalone" } : {}),
  ...(distDir ? { distDir } : {}),
};

export default nextConfig;
