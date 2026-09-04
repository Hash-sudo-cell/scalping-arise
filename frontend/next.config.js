/** @type {import('next').NextConfig} */
const path = require("path");

const nextConfig = {
  reactStrictMode: true,

  // Resolve @/* path alias to src/*
  webpack: (config) => {
    config.resolve.alias["@"] = path.resolve(__dirname, "src");
    return config;
  },

  // Environment variables exposed to the browser (only NEXT_PUBLIC_ prefixed)
  env: {
    NEXT_PUBLIC_APP_NAME: "Scalping Arise",
    NEXT_PUBLIC_APP_VERSION: "1.0.0",
  },
};

module.exports = nextConfig;
