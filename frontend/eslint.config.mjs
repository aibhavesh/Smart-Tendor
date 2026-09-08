import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/*
 * Plan §6.5 — the two theme rules, wired so CI fails the build rather than warning.
 *
 * Scope is src/** only: `scripts/` holds the verification tooling, which necessarily
 * contains the literal values it checks the tokens against. globals.css is not linted
 * by ESLint at all, which is exactly the intent — it is the one sanctioned home for
 * literal colour.
 */
// These land inside an esquery selector's /.../ literal, so they take single
// backslashes — String.raw already prevents JS-level escape processing.
const HEX = String.raw`#[0-9a-fA-F]{3,8}`;
const COLOUR_FN = String.raw`(rgba?|hsla?)\(`;
const ARBITRARY = String.raw`-\[(#[0-9a-fA-F]{3,8}|(rgba?|hsla?)\()`;

const LITERAL_MSG =
  "Literal colour value. Colours live in src/app/globals.css as @theme tokens — use the token utility (bg-brand, text-ink, shadow-cta ...) instead.";
const ARBITRARY_MSG =
  "Arbitrary Tailwind colour value. Add a token to the @theme block in globals.css and use its generated utility instead of bracket syntax.";

const themeRules = [
  { selector: `Literal[value=/${HEX}/]`, message: LITERAL_MSG },
  { selector: `TemplateElement[value.raw=/${HEX}/]`, message: LITERAL_MSG },
  { selector: `Literal[value=/${COLOUR_FN}/]`, message: LITERAL_MSG },
  { selector: `TemplateElement[value.raw=/${COLOUR_FN}/]`, message: LITERAL_MSG },
  { selector: `Literal[value=/${ARBITRARY}/]`, message: ARBITRARY_MSG },
  { selector: `TemplateElement[value.raw=/${ARBITRARY}/]`, message: ARBITRARY_MSG },
];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/**/*.{ts,tsx,js,jsx}"],
    rules: {
      "no-restricted-syntax": ["error", ...themeRules],
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);

export default eslintConfig;
