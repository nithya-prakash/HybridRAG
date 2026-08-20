"use client";

import { useState } from "react";
import type { Citation } from "@/lib/conversations-api";

// There's no per-document viewer/page-jump route in this app yet, so a
// citation chip can't deep-link to the exact page the way a footnote in a
// PDF reader could — it expands in place to show which document/page and
// the excerpt instead. See ARCHITECTURE.md for this documented gap.
export function CitationChips({ citations }: { citations: Citation[] }) {
  const [expandedMarker, setExpandedMarker] = useState<number | null>(null);

  if (citations.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {citations.map((c) => (
        <div key={c.marker} className="relative">
          <button
            onClick={() => setExpandedMarker(expandedMarker === c.marker ? null : c.marker)}
            className="rounded-full border border-slate-700 bg-slate-950 px-2 py-0.5 text-xs text-slate-300 hover:border-slate-500 hover:text-white"
          >
            [{c.marker}] {c.filename}
            {c.page_number != null ? ` p.${c.page_number}` : ""}
          </button>
          {expandedMarker === c.marker && (
            <div className="absolute z-10 mt-1 w-72 rounded-md border border-slate-700 bg-slate-950 p-3 text-xs shadow-lg">
              <p className="font-medium text-slate-200">
                {c.filename}
                {c.page_number != null ? ` — page ${c.page_number}` : ""}
              </p>
              <p className="mt-1 text-slate-400">{c.excerpt}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
