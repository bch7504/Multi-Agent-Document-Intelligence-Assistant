import { useCallback, useEffect, useRef, useState } from "react";
import { ChatWorkspace } from "./components/chat/ChatWorkspace";
import { ModelSettings } from "./components/common/ModelSettings";
import { DocumentPanel } from "./components/documents/DocumentPanel";
import { HistoryPanel } from "./components/history/HistoryPanel";
import { QuizLibrary } from "./components/quiz/QuizLibrary";
import {
  deleteConversation,
  deleteDocument,
  getConversationMessages,
  getModelCatalog,
  listConversations,
  listDocuments,
  listQuizzes,
  MAX_UPLOAD_BYTES,
  MAX_UPLOAD_MEGABYTES,
  renameConversation,
  runAssistant,
  uploadDocument,
} from "./services/api";
import type {
  AssistantTask,
  ChatEntry,
  ConversationSummary,
  DocumentItem,
  ModelCatalog,
  ModelProvider,
  ModelSelection,
  QuizLibraryItem,
} from "./types/api";

function getConversationId(): string {
  const existing = sessionStorage.getItem("atlas-conversation-id");
  if (existing) return existing;
  const created = crypto.randomUUID();
  sessionStorage.setItem("atlas-conversation-id", created);
  return created;
}

function savedModelSelection(catalog: ModelCatalog): ModelSelection | null {
  try {
    const parsed = JSON.parse(localStorage.getItem("atlas-model-selection") ?? "null") as ModelSelection | null;
    if (!parsed?.chat?.provider || !parsed.chat.model || !parsed?.embedding?.provider || !parsed.embedding.model) return null;
    const configured = new Set(catalog.providers.filter((item) => item.configured).map((item) => item.provider));
    if (!configured.has(parsed.chat.provider) || !configured.has(parsed.embedding.provider)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function App() {
  const [conversationId, setConversationId] = useState(() => getConversationId());
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [task, setTask] = useState<AssistantTask>("auto");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [models, setModels] = useState<ModelSelection | null>(null);
  const [modelsOpen, setModelsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [quizLibraryOpen, setQuizLibraryOpen] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [quizzes, setQuizzes] = useState<QuizLibraryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [quizLoading, setQuizLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const runEpoch = useRef(0);
  const initialConversationId = useRef(conversationId);

  const refresh = useCallback(async () => {
    try {
      const response = await listDocuments();
      setDocuments(response.items);
      setSelectedIds((ids) => ids.filter((id) => response.items.some((doc) => doc.id === id && doc.status === "ready")));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load documents");
    }
  }, []);

  const refreshConversations = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const response = await listConversations();
      setConversations(response.items);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const refreshQuizzes = useCallback(async () => {
    setQuizLoading(true);
    try {
      const response = await listQuizzes();
      setQuizzes(response.items);
    } finally {
      setQuizLoading(false);
    }
  }, []);

  const loadConversation = useCallback(async (id: string, closePanel = true) => {
    runEpoch.current += 1;
    const response = await getConversationMessages(id);
    if (!response) return;
    sessionStorage.setItem("atlas-conversation-id", id);
    setConversationId(id);
    setEntries(response.items.map((item) => ({
      id: item.id,
      role: item.role,
      text: item.content,
      task: item.task ?? undefined,
    })));
    setBusy(false);
    setError(null);
    if (closePanel) setHistoryOpen(false);
  }, []);

  useEffect(() => {
    void refresh();
    // A freshly generated thread id does not exist in PostgreSQL until its
    // first successful assistant run. Check history before requesting messages
    // so a legitimate new thread does not generate a noisy 404 in the browser.
    void listConversations()
      .then((response) => {
        setConversations(response.items);
        if (response.items.some((item) => item.id === initialConversationId.current)) {
          return loadConversation(initialConversationId.current, false);
        }
        return undefined;
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load conversation history"));
    void getModelCatalog()
      .then((response) => {
        setCatalog(response);
        setModels((current) => current ?? savedModelSelection(response) ?? {
            chat: response.activeChat,
            embedding: response.activeEmbedding,
          });
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load model catalog"));
  }, [loadConversation, refresh]);

  useEffect(() => {
    const indexed = documents.find(
      (document) => document.status === "ready" && document.embeddingModel,
    )?.embeddingModel;
    if (!indexed) return;
    const separator = indexed.indexOf(":");
    if (separator < 1) return;
    const provider = indexed.slice(0, separator) as ModelProvider;
    const model = indexed.slice(separator + 1);
    setModels((current) => {
      if (!current || (current.embedding.provider === provider && current.embedding.model === model)) return current;
      return { ...current, embedding: { provider, model } };
    });
  }, [documents, models?.embedding.model, models?.embedding.provider]);

  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(null), 2400);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  async function handleUpload(file: File) {
    setError(null);
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF documents can be uploaded");
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      const size = (file.size / (1024 * 1024)).toFixed(1);
      setError(`This PDF is ${size} MB. The upload limit is ${MAX_UPLOAD_MEGABYTES} MB`);
      return;
    }
    setUploading(true);
    try {
      if (!models) throw new Error("Model configuration is still loading");
      const document = await uploadDocument(file, models);
      await refresh();
      if (document.status === "failed") {
        throw new Error(document.errorMessage || "The PDF could not be processed");
      }
      if (document.status === "ready") {
        setSelectedIds((ids) => [...new Set([...ids, document.id])]);
        setNotice(`${document.name} uploaded and indexed`);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Upload failed");
    } finally { setUploading(false); }
  }

  async function handleDelete(id: string) {
    setError(null);
    try { await deleteDocument(id); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Delete failed"); }
  }

  async function handleRun() {
    const input = message.trim();
    if (!input || !selectedIds.length || !models) return;
    const userEntry: ChatEntry = { id: crypto.randomUUID(), role: "user", text: input, task };
    const epoch = runEpoch.current;
    setEntries((items) => [...items, userEntry]); setMessage(""); setBusy(true); setError(null);
    try {
      const result = await runAssistant({ conversationId, documentIds: selectedIds, task, message: input, models });
      if (runEpoch.current === epoch) {
        setEntries((items) => [...items, { id: result.runId, role: "assistant", text: result.answer, task: result.task, result }]);
        void refreshConversations().catch(() => undefined);
        if (result.quiz) void refreshQuizzes().catch(() => undefined);
      }
    } catch (cause) {
      if (runEpoch.current === epoch) setError(cause instanceof Error ? cause.message : "Assistant run failed");
    } finally {
      if (runEpoch.current === epoch) setBusy(false);
    }
  }

  async function handleRenameConversation(id: string, title: string) {
    try {
      await renameConversation(id, title);
      await refreshConversations();
      setNotice("Thread renamed");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not rename thread");
    }
  }

  async function handleDeleteConversation(id: string) {
    if (!window.confirm("Delete this thread, its runs, and saved quizzes?")) return;
    try {
      await deleteConversation(id);
      await Promise.all([refreshConversations(), refreshQuizzes()]);
      if (id === conversationId) resetThread();
      setNotice("Thread deleted");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete thread");
    }
  }

  function resetThread() {
    runEpoch.current += 1;
    const nextConversationId = crypto.randomUUID();
    sessionStorage.setItem("atlas-conversation-id", nextConversationId);
    setConversationId(nextConversationId);
    setEntries([]);
    setMessage("");
    setTask("auto");
    setBusy(false);
    setError(null);
    setNotice("New thread started");
  }

  return (
    <div className="app-shell">
      <DocumentPanel
        documents={documents}
        selectedIds={selectedIds}
        loading={uploading}
        onToggle={(id) => setSelectedIds((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id])}
        onUpload={(file) => void handleUpload(file)}
        onDelete={(id) => void handleDelete(id)}
      />
      <ChatWorkspace
        entries={entries}
        task={task}
        message={message}
        selectedCount={selectedIds.length}
        running={busy}
        models={models}
        onTask={setTask}
        onMessage={setMessage}
        onSubmit={() => void handleRun()}
        onReset={resetThread}
        onOpenModels={() => setModelsOpen(true)}
        onOpenHistory={() => {
          setHistoryOpen(true);
          void refreshConversations().catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load history"));
        }}
        onOpenQuizzes={() => {
          setQuizLibraryOpen(true);
          void refreshQuizzes().catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load quizzes"));
        }}
      />
      {catalog && models && (
        <ModelSettings
          open={modelsOpen}
          catalog={catalog}
          selection={models}
          embeddingLocked={documents.some((document) => document.status === "ready")}
          onApply={(selection) => {
            setModels(selection);
            localStorage.setItem("atlas-model-selection", JSON.stringify(selection));
          }}
          onClose={() => setModelsOpen(false)}
        />
      )}
      <HistoryPanel
        open={historyOpen}
        loading={historyLoading}
        conversations={conversations}
        currentId={conversationId}
        onSelect={(id) => void loadConversation(id).catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load thread"))}
        onRename={(id, title) => void handleRenameConversation(id, title)}
        onDelete={(id) => void handleDeleteConversation(id)}
        onClose={() => setHistoryOpen(false)}
      />
      <QuizLibrary
        open={quizLibraryOpen}
        loading={quizLoading}
        quizzes={quizzes}
        onRefresh={refreshQuizzes}
        onClose={() => setQuizLibraryOpen(false)}
        onError={setError}
        onNotice={setNotice}
      />
      {error && <div className="error-toast"><strong>Request failed</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>}
      {notice && <div className="success-toast" role="status"><span className="success-check">✓</span><span>{notice}</span></div>}
    </div>
  );
}
