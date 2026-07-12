import { useEffect, useRef } from "react";
import { api } from "../api";
import { readThresholdMs } from "./readThreshold";

interface Options {
  documentId: number;
  pageNumber: number;
  wordCount: number;
  // Required for pdf (no paragraph rows); omitted for txt/epub.
  pageText?: string;
  // Gate the timer until the page's content (and word count) is actually loaded.
  enabled: boolean;
}

// Fires once per page visit, when the reader has actively dwelled on the page
// long enough (scaled by word count) that we're confident they read it, and tells
// the backend to commit the page's words to read_words. "Actively" excludes time
// the tab/window is hidden, so leaving a page open in the background doesn't count.
export function usePageReadTimer({
  documentId,
  pageNumber,
  wordCount,
  pageText,
  enabled,
}: Options) {
  // Latest pageText without re-arming the timer when it streams in slightly late.
  const pageTextRef = useRef(pageText);
  pageTextRef.current = pageText;

  useEffect(() => {
    if (!enabled) return;

    const threshold = readThresholdMs(wordCount);
    let accumulated = 0; // active ms banked before the current visible stretch
    let lastResume = document.hidden ? null : Date.now();
    let fired = false;

    const activeMs = () =>
      accumulated + (lastResume !== null ? Date.now() - lastResume : 0);

    const onVisibility = () => {
      if (document.hidden) {
        // Bank the visible stretch and pause.
        if (lastResume !== null) {
          accumulated += Date.now() - lastResume;
          lastResume = null;
        }
      } else if (lastResume === null) {
        lastResume = Date.now();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    const interval = window.setInterval(() => {
      if (fired || activeMs() < threshold) return;
      fired = true;
      window.clearInterval(interval);
      api
        .markPageRead({
          document_id: documentId,
          page_number: pageNumber,
          page_text: pageTextRef.current,
        })
        .catch(() => {});
    }, 1000);

    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
    // pageText intentionally excluded — read live from the ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, pageNumber, wordCount, enabled]);
}
