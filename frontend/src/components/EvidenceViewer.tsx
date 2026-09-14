import { useEffect, useRef, useState } from "react";
import {
  Crosshair,
  Minus,
  Plus,
  ScanSearch,
  ZoomIn,
} from "lucide-react";

import { api } from "@/lib/api";
import { EXTRACTION_MODE_LABELS, type EvidenceOut, type ExtractionMode } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";
import { ErrorState, Loading } from "@/components/ui/State";

/** Evidence viewer: the scanned page with the offending cell highlighted.
 *
 *  This is the component that makes a finding believable. Without it a finding is
 *  an assertion an employer can simply deny; with it, an inspector opens the scan
 *  and sees the cell the figure was read from.
 *
 *  Coordinates arrive normalised to 0-1 rather than as pixels, so a box stays
 *  correct whatever size the image is rendered at and survives the page being
 *  re-rasterised at a different DPI.
 *
 *  A page read without OCR has no coordinates at all. That case is stated plainly
 *  rather than hidden, because evidence quality is exactly what an officer needs
 *  to judge before acting on a finding.
 */

interface EvidenceViewerProps {
  evidence: EvidenceOut;
  /** Other evidence on the same page, drawn faintly for context. */
  siblings?: EvidenceOut[];
}

export function EvidenceViewer({ evidence, siblings = [] }: EvidenceViewerProps) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [zoom, setZoom] = useState(1);
  const [focused, setFocused] = useState(true);

  const containerRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  const documentId = evidence.document_id;
  const pageNumber = evidence.page_number;

  useEffect(() => {
    if (!documentId || pageNumber === null) {
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    let created: string | null = null;

    setLoading(true);
    setError(null);

    void (async () => {
      try {
        const url = await api.objectUrl(
          `/documents/${documentId}/pages/${pageNumber}/image`,
          controller.signal,
        );
        created = url;
        setImageUrl(url);
      } catch (err) {
        if (!controller.signal.aborted) setError(err);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();

    return () => {
      controller.abort();
      // Blob URLs are retained for the document's lifetime unless revoked, and a
      // register page is a few hundred kilobytes each.
      if (created) URL.revokeObjectURL(created);
    };
  }, [documentId, pageNumber]);

  // Scroll the highlight into view once the image has laid out. Without this the
  // box is frequently below the fold on a tall register page and the viewer looks
  // as though it highlighted nothing.
  useEffect(() => {
    if (!imageUrl || !evidence.bbox || !focused) return;
    const timer = window.setTimeout(() => {
      boxRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [imageUrl, evidence.bbox, focused, zoom]);

  if (!documentId || pageNumber === null) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
        <p className="font-bold text-slate-800">No page reference</p>
        <p className="mt-1 leading-relaxed">
          {evidence.note ??
            "This finding was raised from data compared across documents rather than from a single place on a page, so there is no cell to show."}
        </p>
      </div>
    );
  }

  const boxes = [
    { item: evidence, primary: true },
    ...siblings
      .filter((s) => s.page_number === pageNumber && s.bbox && s !== evidence)
      .map((item) => ({ item, primary: false })),
  ];

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone="neutral">Page {pageNumber}</Badge>
          {evidence.field_name && (
            <Badge tone="low">{humaniseField(evidence.field_name)}</Badge>
          )}
          {evidence.value_shown && (
            <Badge tone="pending" className="font-mono">
              {evidence.value_shown}
            </Badge>
          )}
          {evidence.row_reference && (
            <span className="text-slate-500">{evidence.row_reference}</span>
          )}
          {!evidence.is_cell_level && (
            <Badge tone="medium">Page-level evidence only</Badge>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {evidence.bbox && (
            <button
              type="button"
              onClick={() => setFocused((value) => !value)}
              aria-pressed={focused}
              title={focused ? "Show the whole page" : "Focus the highlighted cell"}
              className={[
                "cursor-pointer inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-bold transition-colors",
                focused
                  ? "border-sky-300 bg-sky-600 text-white"
                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
              ].join(" ")}
            >
              <Crosshair className="h-3.5 w-3.5" />
              {focused ? "Focused" : "Focus cell"}
            </button>
          )}

          <div className="flex items-center rounded-full border border-slate-300 bg-white">
            <button
              type="button"
              onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.25).toFixed(2)))}
              disabled={zoom <= 0.5}
              aria-label="Zoom out"
              className="cursor-pointer rounded-l-full px-2.5 py-1.5 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <span className="w-12 text-center font-mono text-xs font-bold text-slate-700">
              {Math.round(zoom * 100)}%
            </span>
            <button
              type="button"
              onClick={() => setZoom((z) => Math.min(4, +(z + 0.25).toFixed(2)))}
              disabled={zoom >= 4}
              aria-label="Zoom in"
              className="cursor-pointer rounded-r-full px-2.5 py-1.5 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Page */}
      <div
        ref={containerRef}
        className="relative max-h-[70vh] overflow-auto rounded-2xl border border-slate-300 bg-slate-100"
      >
        {loading && <Loading label="Loading the scanned page" />}
        {error !== null && <ErrorState error={error} context="the page image" />}

        {imageUrl && (
          <div
            className="relative mx-auto"
            style={{ width: `${zoom * 100}%`, minWidth: "100%" }}
          >
            <img
              src={imageUrl}
              alt={`Page ${pageNumber} of ${evidence.document_filename ?? "the document"}`}
              className="block w-full select-none"
              draggable={false}
            />

            {/* Dim everything but the highlighted cell, so the eye lands on it
                immediately on a page of four hundred numbers. */}
            {focused && evidence.bbox && (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-slate-900/35 transition-opacity"
                style={{
                  clipPath: cutout(evidence.bbox),
                }}
              />
            )}

            {boxes.map(({ item, primary }, index) =>
              item.bbox ? (
                <div
                  key={index}
                  ref={primary ? boxRef : undefined}
                  className={[
                    "pointer-events-none absolute rounded-[3px] transition-all",
                    primary
                      ? "border-2 border-rose-500 shadow-[0_0_0_4px_rgba(244,63,94,0.22)]"
                      : "border-2 border-dashed border-sky-500/70",
                  ].join(" ")}
                  style={boxStyle(item.bbox)}
                >
                  {primary && (
                    <span className="absolute -top-6 left-0 whitespace-nowrap rounded-md bg-rose-600 px-2 py-0.5 text-[11px] font-bold text-white shadow">
                      {item.value_shown ?? humaniseField(item.field_name ?? "evidence")}
                    </span>
                  )}
                </div>
              ) : null,
            )}
          </div>
        )}
      </div>

      {evidence.note && (
        <p className="flex items-start gap-2 text-xs leading-relaxed text-slate-600">
          <ScanSearch aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
          {evidence.note}
        </p>
      )}
    </div>
  );
}

/** A padded rectangle around a normalised bbox, in percentage units so it scales
 *  with the rendered image. Padding is added because a tight box on a scanned
 *  digit is hard to see. */
function boxStyle(bbox: number[]): React.CSSProperties {
  const [left = 0, top = 0, width = 0, height = 0] = bbox;
  const padX = Math.max(0.004, width * 0.12);
  const padY = Math.max(0.006, height * 0.3);

  return {
    left: `${Math.max(0, (left - padX) * 100)}%`,
    top: `${Math.max(0, (top - padY) * 100)}%`,
    width: `${Math.min(1, width + padX * 2) * 100}%`,
    height: `${Math.min(1, height + padY * 2) * 100}%`,
  };
}

/** Clip path that dims the page except for a window over the cell. */
function cutout(bbox: number[]): string {
  const [left = 0, top = 0, width = 0, height = 0] = bbox;
  const padX = Math.max(0.01, width * 0.25);
  const padY = Math.max(0.012, height * 0.6);

  const x1 = Math.max(0, (left - padX) * 100);
  const y1 = Math.max(0, (top - padY) * 100);
  const x2 = Math.min(100, (left + width + padX) * 100);
  const y2 = Math.min(100, (top + height + padY) * 100);

  // Outer rectangle clockwise, inner rectangle anticlockwise: the even-odd fill
  // rule then leaves the inner region uncovered.
  return `polygon(evenodd, 0% 0%, 100% 0%, 100% 100%, 0% 100%, 0% 0%, ${x1}% ${y1}%, ${x1}% ${y2}%, ${x2}% ${y2}%, ${x2}% ${y1}%, ${x1}% ${y1}%)`;
}

function humaniseField(name: string): string {
  return name
    .replace(/_paise$/, " amount")
    .replace(/_/g, " ")
    .replace(/^./, (c) => c.toUpperCase());
}

/** How a page was read, shown beside evidence so an officer can weigh it.
 *  A vision-only page has no cell coordinates and its evidence is weaker. */
export function ExtractionModeNote({ mode }: { mode: ExtractionMode | null }) {
  if (!mode) return null;

  const tone =
    mode === "NATIVE_PDF"
      ? "good"
      : mode === "OCR_ONLY" || mode === "OCR_PLUS_VISION"
        ? "low"
        : "medium";

  return (
    <Badge tone={tone} title={EXTRACTION_MODE_LABELS[mode]}>
      <ZoomIn aria-hidden="true" className="h-3 w-3" />
      {EXTRACTION_MODE_LABELS[mode]}
    </Badge>
  );
}
