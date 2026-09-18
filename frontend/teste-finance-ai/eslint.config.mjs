import { defineConfig, globalIgnores } from "eslint/config";
import { FlatCompat } from "@eslint/eslintrc";
import path from "node:path";
import { fileURLToPath } from "node:url";

// eslint-config-next 15.x ainda publica suas regras no formato antigo
// (.eslintrc "extends"), mas o ESLint 9 só entende "flat config" por
// padrão. O FlatCompat é a ponte oficial entre os dois formatos —
// é o mesmo helper que o `create-next-app` gera para projetos Next 15.
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const compat = new FlatCompat({ baseDirectory: __dirname });

const eslintConfig = defineConfig([
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  // Override default ignores of eslint-config-next.
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
