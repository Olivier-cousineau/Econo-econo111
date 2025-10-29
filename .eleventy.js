export default function(eleventyConfig) {
  const passthroughFiles = [
    "assets",
    "data",
    "logs",
    "api",
    "previews",
    "best-deals.html",
    "best-deals-en.html",
    "best-deals-es.html",
    "best-deals-de.html",
    "best-deals-it.html",
    "pricing.html",
    "pricing-en.html",
    "pricing-es.html",
    "pricing-de.html",
    "pricing-it.html",
    "roadmap.html",
    "roadmap-en.html",
    "roadmap-es.html",
    "roadmap-de.html",
    "roadmap-it.html",
    "index-es.html",
    "index-de.html",
    "index-it.html",
    "archive",
    "vercel.json",
    "server.py",
    "scraper_canadiantire.py",
    "scraper_sportinglife_liquidation.py",
    "requirements.txt"
  ];

  passthroughFiles.forEach(item => {
    eleventyConfig.addPassthroughCopy(item);
  });

  return {
    dir: {
      input: "src",
      includes: "_includes",
      data: "_data",
      output: "_site"
    }
  };
}
