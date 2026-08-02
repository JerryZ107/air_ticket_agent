const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

/** @type {import('next').NextConfig} */
const nextConfig = {
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: "/api/chat",
        destination: `${BACKEND_URL}/api/chat`,
      },
      {
        source: "/api/auth/:path*",
        destination: `${BACKEND_URL}/api/auth/:path*`,
      },
      {
        source: "/api/trace/:path*",
        destination: `${BACKEND_URL}/api/trace/:path*`,
      },
      {
        source: "/chat",
        destination: `${BACKEND_URL}/chat`,
      },
      {
        source: "/chatkit",
        destination: `${BACKEND_URL}/chatkit`,
      },
      {
        source: "/chatkit/:path*",
        destination: `${BACKEND_URL}/chatkit/:path*`,
      },
    ];
  },
};

export default nextConfig;
