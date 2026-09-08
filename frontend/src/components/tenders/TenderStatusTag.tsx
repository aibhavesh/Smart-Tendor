import { TENDER_STATUS_HINT, TENDER_STATUS_LABEL } from "@/lib/tender-status";
import type { TenderStatus } from "@/lib/types";

/*
 * A lifecycle state, told twice: what it means, then the code it is called in the API.
 *
 * The code stays visible because it is the vocabulary of the filter, the audit log and
 * every support conversation — dropping it would make the screen readable and the system
 * harder to talk about. `showCode` turns it off where the row is already tight.
 */
export function TenderStatusTag({
  status,
  showCode = true,
}: {
  status: TenderStatus;
  showCode?: boolean;
}) {
  return (
    <span
      className="inline-flex items-baseline gap-1.5 whitespace-nowrap"
      title={TENDER_STATUS_HINT[status]}
    >
      <span className="text-caption font-semibold text-ink">{TENDER_STATUS_LABEL[status]}</span>
      {showCode ? <span className="text-mini text-ink-muted">{status}</span> : null}
    </span>
  );
}
