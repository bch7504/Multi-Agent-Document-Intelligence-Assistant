import { useEffect, useMemo, useState } from "react";
import type {
  ModelCatalog,
  ModelChoice,
  ModelProvider,
  ModelSelection,
} from "../../types/api";

interface Props {
  open: boolean;
  catalog: ModelCatalog;
  selection: ModelSelection;
  embeddingLocked: boolean;
  onApply: (selection: ModelSelection) => void;
  onClose: () => void;
}

function ChoiceEditor({
  id,
  title,
  value,
  catalog,
  disabled,
  onChange,
}: {
  id: string;
  title: string;
  value: ModelChoice;
  catalog: ModelCatalog;
  disabled?: boolean;
  onChange: (choice: ModelChoice) => void;
}) {
  const provider = catalog.providers.find((item) => item.provider === value.provider);
  const models = id === "chat" ? provider?.chatModels ?? [] : provider?.embeddingModels ?? [];
  return (
    <section className="model-editor">
      <div className="model-editor-heading">
        <div><span className="eyebrow">{id === "chat" ? "Generation" : "Retrieval"}</span><h3>{title}</h3></div>
        {disabled && <span className="locked-badge">Locked by index</span>}
      </div>
      <label>
        Provider
        <select
          value={value.provider}
          disabled={disabled}
          onChange={(event) => {
            const nextProvider = event.target.value as ModelProvider;
            const next = catalog.providers.find((item) => item.provider === nextProvider);
            const nextModels = id === "chat" ? next?.chatModels : next?.embeddingModels;
            onChange({ provider: nextProvider, model: nextModels?.[0] ?? "" });
          }}
        >
          {catalog.providers.map((item) => (
            <option key={item.provider} value={item.provider} disabled={!item.configured}>
              {item.label} · {item.runtime}{item.configured ? "" : " · not configured"}
            </option>
          ))}
        </select>
      </label>
      <label>
        Model ID
        <input
          value={value.model}
          disabled={disabled}
          list={`${id}-model-suggestions`}
          spellCheck={false}
          onChange={(event) => onChange({ ...value, model: event.target.value })}
        />
        <datalist id={`${id}-model-suggestions`}>
          {models.map((model) => <option value={model} key={model} />)}
        </datalist>
      </label>
      <div className="model-provider-state">
        <span className={`provider-state-dot ${provider?.configured ? "ready" : "missing"}`} />
        {provider?.configured
          ? `${provider.label} configuration is available on the server.`
          : `Add the ${provider?.label ?? value.provider} credential/runtime to .env and restart the API.`}
      </div>
    </section>
  );
}

export function ModelSettings(props: Props) {
  const [draft, setDraft] = useState<ModelSelection>(props.selection);
  useEffect(() => { if (props.open) setDraft(props.selection); }, [props.open, props.selection]);
  const valid = useMemo(
    () => Boolean(draft.chat.model.trim() && draft.embedding.model.trim()),
    [draft],
  );
  if (!props.open) return null;
  return (
    <div className="model-dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) props.onClose();
    }}>
      <div className="model-dialog" role="dialog" aria-modal="true" aria-labelledby="model-settings-title">
        <header>
          <div>
            <span className="eyebrow">Runtime configuration</span>
            <h2 id="model-settings-title">Choose project models</h2>
            <p>Credentials stay on the server. The browser sends only provider and model IDs.</p>
          </div>
          <button type="button" className="dialog-close" onClick={props.onClose} aria-label="Close model settings">×</button>
        </header>
        <div className="model-editor-grid">
          <ChoiceEditor
            id="chat"
            title="Chat model"
            value={draft.chat}
            catalog={props.catalog}
            onChange={(chat) => setDraft((current) => ({ ...current, chat }))}
          />
          <ChoiceEditor
            id="embedding"
            title="Embedding model"
            value={draft.embedding}
            catalog={props.catalog}
            disabled={props.embeddingLocked}
            onChange={(embedding) => setDraft((current) => ({ ...current, embedding }))}
          />
        </div>
        <div className="model-warning">
          Embedding dimensions define the Milvus index. Once a ready document exists, the embedding choice is locked until documents are removed and the collection is re-indexed.
        </div>
        <footer>
          <div className="selection-preview">
            <span>Chat <strong>{draft.chat.provider} / {draft.chat.model}</strong></span>
            <span>Embedding <strong>{draft.embedding.provider} / {draft.embedding.model}</strong></span>
          </div>
          <button type="button" className="apply-models" disabled={!valid} onClick={() => {
            props.onApply({
              chat: { ...draft.chat, model: draft.chat.model.trim() },
              embedding: { ...draft.embedding, model: draft.embedding.model.trim() },
            });
            props.onClose();
          }}>Apply models</button>
        </footer>
      </div>
    </div>
  );
}
