import type { Citation } from "../../types/api";

export function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <div className="citation-list">
      <span className="section-label">Sources</span>
      {citations.map((citation, index) => (
        <details className="citation-card" key={citation.chunkId}>
          <summary>
            <span className="source-index">{index + 1}</span>
            <span>{citation.documentName}</span>
            <small>{citation.pageNumber ? `p. ${citation.pageNumber}` : "source"}</small>
          </summary>
          <p>{citation.excerpt}</p>
          {citation.sourceUri && (
            <a href={citation.sourceUri} target="_blank" rel="noreferrer">Open source ↗</a>
          )}
        </details>
      ))}
    </div>
  );
}
