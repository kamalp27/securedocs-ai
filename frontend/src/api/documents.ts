/**
 * Document API services: upload, list, get, download, and delete documents.
 */

import { apiFetch, ApiError, AuthExpiredError, getAccessToken, refreshAccessToken } from './client'
import type { DocumentDetail, DocumentItem, DocumentListResponse } from '../types/api'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const MAX_FILE_SIZE_BYTES = 26214400 // 25 MB
export const SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md']
export const SUPPORTED_MIME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
]

/**
 * Retrieve paginated list of documents owned by the authenticated user.
 */
export async function listDocuments(
  page = 1,
  pageSize = 20,
  status?: string
): Promise<DocumentListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (status) {
    params.set('status', status)
  }

  return apiFetch<DocumentListResponse>(`/api/v1/documents?${params.toString()}`, {
    method: 'GET',
  })
}

/**
 * Retrieve detailed document metadata and chunk snippets.
 */
export async function getDocument(documentId: string): Promise<DocumentDetail> {
  return apiFetch<DocumentDetail>(`/api/v1/documents/${documentId}`, {
    method: 'GET',
  })
}

/**
 * Upload a document file with specified security classification.
 */
export async function uploadDocument(
  file: File,
  classification = 'internal'
): Promise<DocumentItem> {
  if (file.size > MAX_FILE_SIZE_BYTES) {
    throw new ApiError(
      `File exceeds maximum size limit of 25 MB (${(file.size / (1024 * 1024)).toFixed(1)} MB).`,
      413
    )
  }

  const formData = new FormData()
  formData.append('file', file)
  formData.append('classification', classification)

  return apiFetch<DocumentItem>('/api/v1/documents/upload', {
    method: 'POST',
    body: formData,
  })
}

/**
 * Safely stream and download a document binary file.
 */
export async function downloadDocument(
  documentId: string,
  filename: string
): Promise<void> {
  const url = `${API_BASE_URL}/api/v1/documents/${documentId}/download`
  const headers = new Headers()
  const token = getAccessToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  let response: Response
  try {
    response = await fetch(url, {
      method: 'GET',
      credentials: 'include',
      headers,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Network error'
    throw new ApiError(`Network connection error: ${message}`, 0)
  }

  // Handle transparent 401 retry with refreshed token
  if (response.status === 401) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      headers.set('Authorization', `Bearer ${newToken}`)
      try {
        response = await fetch(url, {
          method: 'GET',
          credentials: 'include',
          headers,
        })
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Network error'
        throw new ApiError(`Network connection error: ${message}`, 0)
      }
    } else {
      throw new AuthExpiredError()
    }
  }

  if (!response.ok) {
    let detail = `Download failed with status ${response.status}`
    try {
      const err = await response.json()
      if (err?.detail) {
        detail = err.detail
      }
    } catch {
      // Non-JSON response
    }
    throw new ApiError(detail, response.status)
  }

  const blob = await response.blob()
  const downloadUrl = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = downloadUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(downloadUrl)
}

/**
 * Permanently delete a document, its chunks, and associated stored file.
 */
export async function deleteDocument(documentId: string): Promise<void> {
  await apiFetch<{ message: string }>(`/api/v1/documents/${documentId}`, {
    method: 'DELETE',
  })
}
