const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/bureau-en-gros",
        destination: "/",
      },
    ];
  },

  async exportPathMap(defaultPathMap, { dev, dir, outDir, distDir, buildId }) {
    return {
      ...defaultPathMap,
      "/bureau-en-gros": { page: "/bureau-en-gros" },
    };
  },
};

export default nextConfig;
