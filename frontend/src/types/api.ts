/** TypeScript interfaces for SecureDocs AI API requests, responses, citations, and documents. */

export interface User {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  csrf_token?: string | null;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  original_filename: string;
  page_number?: number | null;
  section?: string | null;
  quoted_snippet?: string | null;
}

export interface RetrievedChunkDiagnostic {
  chunk_id: string;
  document_id: string;
  original_filename: string;
  similarity_score: number;
  page_number?: number | null;
  section?: string | null;
}

export interface QARequest {
  question: string;
  top_k?: number;
  similarity_threshold?: number;
  provider?: string | null;
}

export interface QAResponse {
  question: string;
  answer: string;
  citations: Citation[];
  insufficient_evidence: boolean;
  provider: string;
  retrieved_chunk_count: number;
  retrieved_chunks: RetrievedChunkDiagnostic[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  citations?: Citation[];
  insufficient_evidence?: boolean;
  provider?: string;
  retrieved_chunk_count?: number;
  error?: string | null;
}

export interface DocumentItem {
  id: string;
  title: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  sha256_checksum: string;
  classification: string;
  status: string; // "indexed" | "pending" | "failed"
  created_at: string;
  updated_at: string;
  chunk_count: number;
}

export interface DocumentChunkItem {
  id: string;
  chunk_index: number;
  content: string;
  token_count: number;
  metadata_json?: Record<string, unknown> | null;
}

export interface DocumentDetail extends DocumentItem {
  chunks: DocumentChunkItem[];
}

export interface DocumentListResponse {
  items: DocumentItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
