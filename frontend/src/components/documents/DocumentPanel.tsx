import { useRef, useState } from "react";
import { MAX_UPLOAD_MEGABYTES } from "../../services/api";
import type { DocumentItem } from "../../types/api";

interface Props {
  documents: DocumentItem[];
  selectedIds: string[];
  loading: boolean;
  onToggle: (id: string) => void;
  onUpload: (file: File) => void;
  onDelete: (id: string) => void;
}

export function DocumentPanel({
  documents,
  selectedIds,
  loading,
  onToggle,
  onUpload,
  onDelete,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  return (
    <aside className="documents-panel">
      <div className="brand">
        <span className="brand-mark">A</span>
        <div><strong>Atlas</strong><span>Document intelligence</span></div>
      </div>

      <div className="panel-heading">
        <div><span className="eyebrow">Knowledge base</span><h2>Documents</h2></div>
        <span className="count-pill">{documents.length}</span>
      </div>

      <button
        className="upload-zone"
        type="button"
        disabled={loading}
        onClick={() => inputRef.current?.click()}
      >
        <span className="upload-icon">↑</span>
        <strong>{loading ? "Indexing document…" : "Upload a PDF"}</strong>
        <small>Text PDFs · up to {MAX_UPLOAD_MEGABYTES} MB</small>
      </button>
      <input
        ref={inputRef}
        hidden
        type="file"
        accept="application/pdf,.pdf"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onUpload(file);
          event.currentTarget.value = "";
        }}
      />

      <div className="document-list">
        {documents.length === 0 && (
          <div className="empty-documents">
            <span>◇</span>
            <p>No documents yet.</p>
            <small>Upload a PDF to start asking grounded questions.</small>
          </div>
        )}
        {documents.map((document) => {
          const ready = document.status === "ready";
          const selected = selectedIds.includes(document.id);
          const importedJson = document.sourceType === "json";
          const expanded = expandedIds.includes(document.id);
          const sections = document.sections ?? [];
          return (
            <div className={`document-card ${selected ? "selected" : ""}`} key={document.id}>
              <div className="document-card-head">
                <button
                  type="button"
                  className="document-select"
                  disabled={!ready}
                  onClick={() => onToggle(document.id)}
                >
                  <span className="pdf-icon">{importedJson ? "JSON" : "PDF"}</span>
                  <span className="document-copy">
                    <strong title={document.name}>{document.name}</strong>
                    <small>
                      {ready
                        ? importedJson
                          ? sections.length > 0
                            ? `${sections.length} documents · ${document.chunkCount ?? 0} chunks`
                            : `${document.chunkCount ?? 0} chunks`
                          : `${document.pageCount ?? 0} pages · ${document.chunkCount ?? 0} chunks`
                        : document.status}
                    </small>
                  </span>
                  <span className={`status-dot ${document.status}`} title={document.status} />
                </button>
                {sections.length > 0 && (
                  <button
                    className="sections-toggle"
                    type="button"
                    aria-expanded={expanded}
                    aria-label={`${expanded ? "Hide" : "Show"} documents in ${document.name}`}
                    onClick={() => setExpandedIds((ids) => ids.includes(document.id)
                      ? ids.filter((id) => id !== document.id)
                      : [...ids, document.id])}
                  >
                    <span>{sections.length}</span>
                    <b>{expanded ? "−" : "+"}</b>
                  </button>
                )}
              </div>
              <button
                className="delete-button"
                type="button"
                aria-label={`Delete ${document.name}`}
                onClick={() => onDelete(document.id)}
              >
                ×
              </button>
              {expanded && sections.length > 0 && (
                <div className="document-sections">
                  <div className="sections-caption">Documents in this dataset</div>
                  {sections.map((section, index) => (
                    <div className="document-section" key={section.id}>
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <div>
                        <strong title={section.title}>{section.title}</strong>
                        <small>{section.chunkCount} {section.chunkCount === 1 ? "chunk" : "chunks"}</small>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="sidebar-foot">
        <span className="online-dot" /> API connected
        <small>{selectedIds.length} selected</small>
      </div>
    </aside>
  );
}
