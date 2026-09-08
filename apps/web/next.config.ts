import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";
import path from "node:path";

// Share the root .env with Compose and FastAPI.
loadEnvConfig(path.resolve(process.cwd(), "../.."));
const nextConfig: NextConfig = {};
export default nextConfig;
