import fs from "fs";
import path from "path";

const localesDir = path.resolve("locales");

const loadLocales = () => {
  const locales = {};
  if (!fs.existsSync(localesDir)) {
    return locales;
  }

  for (const locale of fs.readdirSync(localesDir)) {
    const localePath = path.join(localesDir, locale);
    if (!fs.statSync(localePath).isDirectory()) {
      continue;
    }

    locales[locale] = {};

    for (const file of fs.readdirSync(localePath)) {
      if (!file.endsWith(".json")) {
        continue;
      }

      const key = file.replace(/\.json$/, "");
      const filePath = path.join(localePath, file);
      const fileContents = fs.readFileSync(filePath, "utf-8");
      locales[locale][key] = JSON.parse(fileContents);
    }
  }

  return locales;
};

export default loadLocales();
