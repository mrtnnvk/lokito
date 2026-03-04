/**
 * Client-safe version of normalize (no Node.js dependencies).
 * Re-exports the same functions — normalize.ts is already client-safe,
 * but this file makes the intention explicit for imports in "use client" components.
 */

export { normalizeStreet, removeDiacritics, getUniqueStreets } from "./normalize";
