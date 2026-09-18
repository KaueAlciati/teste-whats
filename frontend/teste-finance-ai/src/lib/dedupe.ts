/**
 * Espelha `backend/app/core/dedupe.py` — mesma regra de negócio em
 * TypeScript, usada pela importação de extrato e pelas transações
 * manuais no modo LocalStorage, para o mesmo mecanismo de detecção
 * de duplicados existir nos dois modos (API e local).
 *
 * O hash aqui não precisa ser criptográfico (não é usado para
 * segurança, só para identidade de deduplicação local), então usamos
 * um hash simples e determinístico (FNV-1a 32 bits) em vez de SHA-256
 * — evita depender de `crypto.subtle`, que é assíncrono.
 */

const NOISE_PATTERN = /[^a-z0-9 ]+/g;
const MULTI_SPACE = /\s+/g;

export function normalizeDescription(description: string): string {
  let text = (description ?? "").trim().toLowerCase();
  text = text.replace(NOISE_PATTERN, " ");
  text = text.replace(MULTI_SPACE, " ").trim();
  return text;
}

function fnv1aHex(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  // Duas passadas com sementes diferentes para reduzir colisão em
  // relação a um FNV-1a de 32 bits isolado (suficiente para
  // deduplicação local, não para uso criptográfico).
  let hash2 = 0x9e3779b9;
  for (let i = 0; i < input.length; i++) {
    hash2 ^= input.charCodeAt(i);
    hash2 = Math.imul(hash2, 0x85ebca6b);
  }
  const part1 = (hash >>> 0).toString(16).padStart(8, "0");
  const part2 = (hash2 >>> 0).toString(16).padStart(8, "0");
  return part1 + part2;
}

export function computeDedupeHash(
  date: string,
  normalizedDescription: string,
  amount: number,
  type: string,
): string {
  const amountKey = amount.toFixed(2);
  const payload = [date, normalizedDescription, amountKey, type].join("|");
  return fnv1aHex(payload);
}
