/*
 * The localStorage key for the theme, and nothing else.
 *
 * Deliberately its own module with NO "use client" directive. The pre-paint
 * script is built in layout.tsx, a *server* component; importing this from
 * theme.tsx instead would hand the server a client-reference proxy rather than
 * the string, and the key would interpolate into the script as a stub that
 * throws. The saved preference would then never be read back on load.
 *
 * A plain module is importable from both sides, so both get the same string.
 */
export const THEME_STORAGE_KEY = "ti-theme";
