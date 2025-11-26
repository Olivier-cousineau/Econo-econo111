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
      "/bureau-en-gros": { page: "/" },

    };
  },
};

export default nextConfig;
