import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { Loader2 } from "lucide-react";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

// Renders every page of a PDF Blob to canvas, fitted to the container width.
export const PdfPages = ({ blob, onError }) => {
  const wrapRef = useRef(null);
  const [pages, setPages] = useState(0);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(Math.min(el.clientWidth - 16, 1000)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={wrapRef} className="w-full h-full overflow-auto flex flex-col items-center gap-3 py-3" data-testid="receipt-pdf">
      <Document file={blob} onLoadSuccess={({ numPages }) => setPages(numPages)} onLoadError={onError} onSourceError={onError}
        loading={<Loader2 className="w-8 h-8 text-white animate-spin mt-20" />}>
        {Array.from({ length: pages }, (_, i) => (
          <Page key={i} pageNumber={i + 1} width={width} className="mb-3 shadow-2xl" renderTextLayer={false} renderAnnotationLayer={false} />
        ))}
      </Document>
      {pages > 1 && <p className="text-xs text-white/60 pb-2">{pages} стр.</p>}
    </div>
  );
};

