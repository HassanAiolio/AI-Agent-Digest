/** @type {import('next').NextConfig} */
const nextConfig = {
  // Was `output: "export"` (fully static) until /api/feedback needed a real
  // serverless function to commit votes back to the repo. Vercel still
  // prerenders every page at build time same as before; this only adds one
  // live route.
  trailingSlash: true,
};
export default nextConfig;
