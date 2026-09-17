export type AssistantTask = "qa" | "summary" | "quiz";
export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";
export type ModelProvider = "openrouter" | "openai" | "gemini" | "ollama";

export interface ModelChoice {
  provider: ModelProvider;
  model: string;
}

export interface ModelSelection {
  chat: ModelChoice;
  embedding: ModelChoice;
}

export interface ProviderCatalog {
  provider: ModelProvider;
  label: string;
  runtime: "cloud" | "local";
  configured: boolean;
  chatModels: string[];
  embeddingModels: string[];
}

export interface ModelCatalog {
  activeChat: ModelChoice;
  activeEmbedding: ModelChoice;
  providers: ProviderCatalog[];
  embeddingChangeRequiresReindex: boolean;
}

export interface DocumentItem {
  id: string;
  name: string;
  mimeType: string;
  sourceType: string;
  sourceUri: string | null;
  checksum: string;
  status: DocumentStatus;
  pageCount: number | null;
  chunkCount: number | null;
  sections: DocumentSection[];
  embeddingModel: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface DocumentSection {
  id: string;
  title: string;
  startChunkIndex: number;
  endChunkIndex: number;
  chunkCount: number;
}

export interface DocumentListResponse {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface Citation {
  documentId: string;
  documentName: string;
  pageNumber: number | null;
  chunkId: string;
  excerpt: string;
  sourceUri: string | null;
}

export interface TraceStep {
  id: string;
  label: string;
  detail: string;
  durationMs: number;
  status: "complete" | "running" | "failed";
}

export interface QuizQuestion {
  id: string;
  question: string;
  options: Array<{ id: string; text: string }>;
  correctOptionId: string;
  explanation: string;
  citations: Citation[];
}

export interface AssistantResponse {
  runId: string;
  task: AssistantTask;
  answer: string;
  citations: Citation[];
  quiz: { questions: QuizQuestion[] } | null;
  review: {
    status: "pass" | "fail";
    retryCount: number;
    feedback: string | null;
  };
  trace: TraceStep[];
  usage: {
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
  };
}

export interface ChatEntry {
  id: string;
  role: "user" | "assistant";
  text: string;
  task?: AssistantTask;
  result?: AssistantResponse;
}
