import { useState } from "react";
import type { ConversationSummary } from "../../types/api";

interface Props {
  open: boolean;
  loading: boolean;
  conversations: ConversationSummary[];
  currentId: string;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function HistoryPanel(props: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  if (!props.open) return null;

  return (
    <div className="library-backdrop" role="presentation" onMouseDown={props.onClose}>
      <section className="library-panel" role="dialog" aria-modal="true" aria-label="Chat history" onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div><span className="eyebrow">Saved conversations</span><h2>Chat history</h2></div>
          <button className="dialog-close" type="button" onClick={props.onClose}>×</button>
        </header>
        <div className="library-body">
          {props.loading && <div className="library-empty">Loading conversations…</div>}
          {!props.loading && props.conversations.length === 0 && (
            <div className="library-empty"><strong>No saved threads yet</strong><span>Your first completed assistant run will appear here.</span></div>
          )}
          {props.conversations.map((conversation) => (
            <article className={`history-row ${conversation.id === props.currentId ? "active" : ""}`} key={conversation.id}>
              {editingId === conversation.id ? (
                <form className="history-rename" onSubmit={(event) => {
                  event.preventDefault();
                  const title = draftTitle.trim();
                  if (title) props.onRename(conversation.id, title);
                  setEditingId(null);
                }}>
                  <input value={draftTitle} maxLength={255} autoFocus onChange={(event) => setDraftTitle(event.target.value)} />
                  <button type="submit">Save</button>
                  <button type="button" onClick={() => setEditingId(null)}>Cancel</button>
                </form>
              ) : (
                <>
                  <button className="history-open" type="button" onClick={() => props.onSelect(conversation.id)}>
                    <strong>{conversation.title || "Untitled conversation"}</strong>
                    <span>{conversation.messageCount} messages · {formatDate(conversation.updatedAt)}</span>
                  </button>
                  <div className="row-actions">
                    <button type="button" onClick={() => {
                      setEditingId(conversation.id);
                      setDraftTitle(conversation.title || "Untitled conversation");
                    }}>Rename</button>
                    <button className="danger" type="button" onClick={() => props.onDelete(conversation.id)}>Delete</button>
                  </div>
                </>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
