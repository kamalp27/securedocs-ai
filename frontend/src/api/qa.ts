/**
 * Grounded Q&A API service for submitting questions to authorized documents.
 */

import { apiFetch } from './client'
import type { QARequest, QAResponse } from '../types/api'

export async function askQuestion(request: QARequest): Promise<QAResponse> {
  const payload: Record<string, unknown> = {
    question: request.question.trim(),
  }

  if (request.top_k !== undefined) {
    payload.top_k = request.top_k
  }

  if (request.similarity_threshold !== undefined) {
    payload.similarity_threshold = request.similarity_threshold
  }

  if (request.provider && request.provider.trim()) {
    payload.provider = request.provider.trim()
  }

  return apiFetch<QAResponse>('/api/v1/qa/ask', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
