import { useEffect, useMemo, useState } from "react";
import { validateModels } from "../../services/api";
import type {
  ModelCatalog,
  ModelChoice,
  ModelProvider,
  ModelSelection,
  ModelValidationResponse,
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
  onChange,
}: {
  id: string;
  title: string;
  value: ModelChoice;
  catalog: ModelCatalog;
  onChange: (choice: ModelChoice) => void;
}) {
  const provider = catalog.providers.find((item) => item.provider === value.provider);
  const models = id === "chat" ? provider?.chatModels ?? [] : provider?.embeddingModels ?? [];
  return (
    <section className="model-editor">
      <div className="model-editor-heading">
        <div><span className="eyebrow">{id === "chat" ? "Generation" : "Retrieval"}</span><h3>{title}</h3></div>
      </div>
      <label>
        Provider
        <select
          value={value.provider}
          onChange={(event) => {
            const nextProvider = event.target.value as ModelProvider;
            const next = catalog.providers.find((item) => item.provider === nextProvider);
            const nextModels = id === "chat" ? next?.chatModels : next?.embeddingModels;
            onChange({ provider: nextProvider, model: nextModels?.[0] ?? "" });
          }}
        >
          {catalog.providers.map((item) => (
            <option key={item.provider} value={item.provider}>
              {item.label} · {item.runtime}{item.configured ? "" : " · not configured"}
            </option>
          ))}
        </select>
      </label>
      <label>
        Model ID
        <input
          value={value.model}
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
          ? `${provider.label} credential/runtime detected. Apply to verify this model ID.`
          : `${provider?.label ?? value.provider} is not configured yet. You can select it, then Apply to test.`}
      </div>
    </section>
  );
}

export function ModelSettings(props: Props) {
  const [draft, setDraft] = useState<ModelSelection>(props.selection);
  const [validation, setValidation] = useState<ModelValidationResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  useEffect(() => {
    if (!props.open) return;
    setDraft(props.selection);
    setValidation(null);
    setValidationError(null);
  }, [props.open, props.selection]);
  const valid = useMemo(
    () => Boolean(draft.chat.model.trim() && draft.embedding.model.trim()),
    [draft],
  );

  function updateDraft(next: ModelSelection) {
    setDraft(next);
    setValidation(null);
    setValidationError(null);
  }

  async function applyAndValidate() {
    const selection: ModelSelection = {
      chat: { ...draft.chat, model: draft.chat.model.trim() },
      embedding: { ...draft.embedding, model: draft.embedding.model.trim() },
    };
    setChecking(true);
    setValidation(null);
    setValidationError(null);
    try {
      let result = await validateModels(selection);
      const embeddingChanged = props.embeddingLocked && (
        selection.embedding.provider !== props.selection.embedding.provider
        || selection.embedding.model !== props.selection.embedding.model
      );
      if (embeddingChanged) {
        result = {
          ...result,
          usable: false,
          embedding: {
            usable: false,
            message: "Model is reachable, but existing documents use another embedding. Re-index documents before switching.",
          },
        };
      }
      setValidation(result);
      if (result.usable) props.onApply(selection);
    } catch (cause) {
      setValidationError(cause instanceof Error ? cause.message : "Could not validate models");
    } finally {
      setChecking(false);
    }
  }
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
            onChange={(chat) => updateDraft({ ...draft, chat })}
          />
          <ChoiceEditor
            id="embedding"
            title="Embedding model"
            value={draft.embedding}
            catalog={props.catalog}
            onChange={(embedding) => updateDraft({ ...draft, embedding })}
          />
        </div>
        <div className="model-warning">
          You may test any provider and model ID. Changing embeddings while documents are already indexed will be reported as unavailable until those documents are re-indexed.
        </div>
        {(validation || validationError) && (
          <div className={`model-validation ${validation?.usable ? "usable" : "unusable"}`} role="status">
            <strong>{validation?.usable ? "Models are ready to use" : "Models cannot be applied"}</strong>
            {validation ? (
              <div>
                <span><b>Chat</b>{validation.chat.message}</span>
                <span><b>Embedding</b>{validation.embedding.message}</span>
              </div>
            ) : <p>{validationError}</p>}
          </div>
        )}
        <footer>
          <div className="selection-preview">
            <span>Chat <strong>{draft.chat.provider} / {draft.chat.model}</strong></span>
            <span>Embedding <strong>{draft.embedding.provider} / {draft.embedding.model}</strong></span>
          </div>
          <button type="button" className="apply-models" disabled={!valid || checking} onClick={() => void applyAndValidate()}>
            {checking ? "Testing models…" : "Apply & test"}
          </button>
        </footer>
      </div>
    </div>
  );
}
