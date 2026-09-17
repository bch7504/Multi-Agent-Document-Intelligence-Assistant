import type {
  AssistantResponse,
  AssistantTask,
  DocumentItem,
  DocumentListResponse,
  ModelCatalog,
  ModelSelection,
} from "../types/api";

const API_URL = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  let detail = `Request failed (${response.status})`;
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") detail = payload.detail;
    else if (payload.detail) detail = JSON.stringify(payload.detail);
  } catch {
    // Keep the status-based message when the server did not return JSON.
  }
  throw new Error(detail);
}

export async function listDocuments(): Promise<DocumentListResponse> {
  return parseResponse(await fetch(`${API_URL}/documents?limit=100`));
}

export async function getModelCatalog(): Promise<ModelCatalog> {
  return parseResponse(await fetch(`${API_URL}/models`));
}

export async function uploadDocument(
  file: File,
  models: ModelSelection,
): Promise<DocumentItem> {
  const body = new FormData();
  body.append("file", file);
  body.append("embedding_provider", models.embedding.provider);
  body.append("embedding_model", models.embedding.model);
  return parseResponse(
    await fetch(`${API_URL}/documents`, { method: "POST", body }),
  );
}

export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(`${API_URL}/documents/${documentId}`, {
    method: "DELETE",
  });
  if (!response.ok) await parseResponse(response);
}

export async function runAssistant(input: {
  conversationId: string;
  documentIds: string[];
  task: AssistantTask;
  message: string;
  models: ModelSelection;
}): Promise<AssistantResponse> {
  const { models, ...request } = input;
  return parseResponse(
    await fetch(`${API_URL}/assistant/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...request,
        llmProvider: models.chat.provider,
        llmModel: models.chat.model,
        embeddingProvider: models.embedding.provider,
        embeddingModel: models.embedding.model,
      }),
    }),
  );
}
