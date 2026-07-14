/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",        // fully static; rebuilt on every data commit
  trailingSlash: true,
};
export default nextConfig;
