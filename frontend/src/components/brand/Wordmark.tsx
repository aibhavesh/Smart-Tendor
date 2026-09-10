import Link from "next/link";
import { FileSearch } from "lucide-react";

/*
 * The company name, in one place.
 *
 * It was previously spelled out at each of the three lockups — landing navbar, auth
 * header, app shell — which is exactly how the auth screen came to be carrying a
 * different name from the front door. Every surface now reads from BRAND_NAME.
 *
 * Size and display are the caller's, because the three differ: the landing wordmark is
 * display-scale, the app shell's fits a 64px bar. The base string deliberately omits
 * `flex`/`inline-flex` and a text size so a caller's choice can never collide with one
 * baked in here.
 */

export const BRAND_NAME = "Maheshwari Computers";

const BASE = "font-fustat font-extrabold tracking-tight text-ink-strong items-center gap-2";

export function Wordmark({
  className = "",
  iconClassName = "w-6 h-6",
}: {
  /** Must supply the display mode (`flex`/`inline-flex`) and the text size token. */
  className?: string;
  iconClassName?: string;
}) {
  return (
    <Link href="/" className={`${BASE} ${className}`}>
      <FileSearch className={`${iconClassName} text-brand`} aria-hidden="true" />
      {BRAND_NAME}
    </Link>
  );
}
