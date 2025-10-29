const REGISTRATIONS_KEY = 'econodealRegistrations';
const CLIENT_COUNT_KEY = 'econodealClientCount';
const CLIENT_REGISTERED_KEY = 'econodealClientRegistered';
const USER_KEY = 'econodealUser';

export function safeGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (err) {
    console.warn('Stockage local indisponible', err);
    return null;
  }
}

export function safeSet(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (err) {
    console.warn("Impossible d'enregistrer les données", err);
  }
}

export function safeRemove(key) {
  try {
    window.localStorage.removeItem(key);
  } catch (err) {
    console.warn('Impossible de retirer la donnée', err);
  }
}

export function parseJson(value) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch (err) {
    console.warn('Impossible de lire les données existantes', err);
    return null;
  }
}

function cleanText(value) {
  return typeof value === 'string' ? value.trim() : '';
}

export function readRegistrations() {
  const parsed = parseJson(safeGet(REGISTRATIONS_KEY));
  if (!Array.isArray(parsed)) return [];
  return parsed
    .filter((item) => Boolean(item) && typeof item === 'object')
    .map((item) => ({
      name: cleanText(item.name),
      email: cleanText(item.email).toLowerCase(),
      registeredAt: cleanText(item.registeredAt),
    }))
    .filter((item) => item.email.length > 0);
}

export function writeRegistrations(entries) {
  safeSet(REGISTRATIONS_KEY, JSON.stringify(entries));
}

export function upsertRegistration(entry) {
  const collection = readRegistrations();
  const email = cleanText(entry.email).toLowerCase();
  if (!email) return;

  const normalized = {
    name: cleanText(entry.name),
    email,
    registeredAt: cleanText(entry.registeredAt),
  };

  const existingIndex = collection.findIndex((item) => item.email === email);
  if (existingIndex >= 0) {
    collection[existingIndex] = {
      ...collection[existingIndex],
      ...normalized,
    };
  } else {
    collection.push(normalized);
  }

  writeRegistrations(collection);
}

function parseCount(value) {
  const parsed = Number.parseInt(value ?? '0', 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

export function readClientCount() {
  return parseCount(safeGet(CLIENT_COUNT_KEY));
}

export function writeClientCount(value) {
  const normalized = Math.max(0, Number.isFinite(value) ? value : 0);
  safeSet(CLIENT_COUNT_KEY, String(normalized));
  return normalized;
}

export function deriveClientCountFromRegistrations() {
  const registrations = readRegistrations();
  if (!registrations.length) return 0;
  const uniqueEmails = new Set();
  registrations.forEach((item) => {
    if (item && item.email) uniqueEmails.add(item.email);
  });
  return uniqueEmails.size;
}

export function resolveClientCount() {
  const stored = readClientCount();
  const derived = deriveClientCountFromRegistrations();
  const resolved = Math.max(stored, derived);
  if (resolved !== stored) {
    writeClientCount(resolved);
  }
  return resolved;
}

export function isClientRegistered() {
  return safeGet(CLIENT_REGISTERED_KEY) === 'true';
}

export function markClientRegistered() {
  safeSet(CLIENT_REGISTERED_KEY, 'true');
}

export function saveUserPayload(payload) {
  safeSet(USER_KEY, JSON.stringify(payload));
}

export function createNumberFormatter(locale) {
  try {
    return new Intl.NumberFormat(locale);
  } catch (_err) {
    return new Intl.NumberFormat('fr-CA');
  }
}

export function createCurrencyFormatter(locale, currency) {
  try {
    return new Intl.NumberFormat(locale, { style: 'currency', currency });
  } catch (_err) {
    return new Intl.NumberFormat('fr-CA', { style: 'currency', currency: 'CAD' });
  }
}

export function createPercentFormatter(locale) {
  try {
    return new Intl.NumberFormat(locale, { maximumFractionDigits: 1, minimumFractionDigits: 0 });
  } catch (_err) {
    return new Intl.NumberFormat('fr-CA', { maximumFractionDigits: 1, minimumFractionDigits: 0 });
  }
}
