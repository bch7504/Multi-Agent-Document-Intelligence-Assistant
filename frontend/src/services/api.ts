import type {
  AssistantResponse,
  AssistantTask,
  ConversationListResponse,
  ConversationMessageList,
  ConversationSummary,
  DocumentItem,
  DocumentListResponse,
  ModelCatalog,
  ModelSelection,
  ModelValidationResponse,
  QuizAttempt,
  QuizAttemptList,
  QuizListResponse,
  SavedQuiz,
} from "../types/api";

const API_URL = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");

export const MAX_UPLOAD_BYTES = 75 * 1024 * 1024;
export const MAX_UPLOAD_MEGABYTES = MAX_UPLOAD_BYTES / (1024 * 1024);

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  if (response.status === 413) {
    throw new Error(`PDF exceeds the ${MAX_UPLOAD_MEGABYTES} MB upload limit`);
  }
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

export async function validateModels(
  models: ModelSelection,
): Promise<ModelValidationResponse> {
  return parseResponse(
    await fetch(`${API_URL}/models/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(models),
    }),
  );
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

export async function listConversations(): Promise<ConversationListResponse> {
  return parseResponse(await fetch(`${API_URL}/conversations?limit=100`));
}

export async function getConversationMessages(
  conversationId: string,
): Promise<ConversationMessageList | null> {
  const response = await fetch(`${API_URL}/conversations/${conversationId}/messages`);
  if (response.status === 404) return null;
  return parseResponse(response);
}

export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<ConversationSummary> {
  return parseResponse(
    await fetch(`${API_URL}/conversations/${conversationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  );
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetch(`${API_URL}/conversations/${conversationId}`, {
    method: "DELETE",
  });
  if (!response.ok) await parseResponse(response);
}

export async function listQuizzes(): Promise<QuizListResponse> {
  return parseResponse(await fetch(`${API_URL}/quizzes?limit=100`));
}

export async function getQuiz(quizId: string): Promise<SavedQuiz> {
  return parseResponse(await fetch(`${API_URL}/quizzes/${quizId}`));
}

export async function listQuizAttempts(quizId: string): Promise<QuizAttemptList> {
  return parseResponse(await fetch(`${API_URL}/quizzes/${quizId}/attempts`));
}

export async function submitQuizAttempt(
  quizId: string,
  answers: Record<string, string>,
): Promise<QuizAttempt> {
  return parseResponse(
    await fetch(`${API_URL}/quizzes/${quizId}/attempts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    }),
  );
}

export async function deleteQuiz(quizId: string): Promise<void> {
  const response = await fetch(`${API_URL}/quizzes/${quizId}`, {
    method: "DELETE",
  });
  if (!response.ok) await parseResponse(response);
}
