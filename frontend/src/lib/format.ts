/** Display formatting.
 *
 *  Two things here are not cosmetic.
 *
 *  Money arrives as integer paise and is divided only at the point of display.
 *  Converting earlier would put a float into the data path, and these figures
 *  decide whether a worker was underpaid.
 *
 *  Indian digit grouping (1,50,000 rather than 150,000) is used throughout,
 *  because the audience reads amounts in lakhs.
 */

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const INR_COMPACT = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const NUMBER = new Intl.NumberFormat("en-IN");

/** Paise to rupees. Null-safe: a missing amount renders as an em dash rather
 *  than as zero, because "not recorded" and "nil" are different findings. */
export function paise(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return INR.format(value / 100);
}

/** Paise to rupees with no decimals, for headline figures. */
export function paiseCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return INR_COMPACT.format(value / 100);
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return NUMBER.format(value);
}

export function percent(
  value: number | null | undefined,
  digits = 0,
): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}%`;
}

/** A 0-1 ratio as a percentage. */
export function ratio(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function bytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

/** An ISO date as "12 Mar 2026". Date-only, no timezone shifting. */
export function date(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value.length <= 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A period as a single readable range, collapsing a whole calendar month to
 *  "March 2026" since that is how wage periods are actually spoken about. */
export function period(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  if (!start && !end) return "Period not determined";
  if (start && end) {
    const from = new Date(`${start}T00:00:00`);
    const to = new Date(`${end}T00:00:00`);
    if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
      return `${start} – ${end}`;
    }

    const isWholeMonth =
      from.getDate() === 1 &&
      from.getMonth() === to.getMonth() &&
      from.getFullYear() === to.getFullYear() &&
      to.getDate() ===
        new Date(to.getFullYear(), to.getMonth() + 1, 0).getDate();

    if (isWholeMonth) {
      return from.toLocaleDateString("en-IN", {
        month: "long",
        year: "numeric",
      });
    }
    return `${date(start)} – ${date(end)}`;
  }
  return date(start ?? end);
}

/** Relative time, for "uploaded 4 minutes ago". Falls back to an absolute date
 *  beyond a week, where relative phrasing stops being informative. */
export function relative(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;

  const seconds = Math.round((Date.now() - parsed.getTime()) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 90) return "a minute ago";

  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minutes ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return hours === 1 ? "an hour ago" : `${hours} hours ago`;

  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;

  return date(value);
}

/** Turn an enum-ish key into a readable label, for keys that have no explicit
 *  label map — observed/expected blobs on a finding, for instance. */
export function humanise(key: string): string {
  const cleaned = key.replace(/_paise$/, "").replace(/[_.]/g, " ").trim();
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

/** Render an arbitrary value from a JSON blob for display.
 *  Keys ending in `_paise` are rendered as currency, so a finding's observed
 *  values read as amounts rather than as large integers. */
export function jsonValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";

  if (typeof value === "number") {
    if (key.endsWith("_paise")) return paise(value);
    if (key.endsWith("_share") || key === "ratio") return ratio(value, 1);
    return Number.isInteger(value) ? count(value) : value.toFixed(2);
  }

  if (Array.isArray(value)) {
    return value.length ? value.map((v) => String(v)).join(", ") : "none";
  }

  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${humanise(k)}: ${jsonValue(k, v)}`)
      .join("; ");
  }

  return String(value);
}

/** Truncate for a table cell without cutting mid-word where avoidable. */
export function truncate(value: string, max = 60): string {
  if (value.length <= max) return value;
  const slice = value.slice(0, max);
  const space = slice.lastIndexOf(" ");
  return `${space > max * 0.6 ? slice.slice(0, space) : slice}…`;
}
