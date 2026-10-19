/**
 * HTTP API client for SecureDocs AI.
 * Handles token attachment, transparent token rotation on 401 using secure HttpOnly cookies,
 * anti-CSRF token synchronization, and safe error normalization.
 */

import type { TokenResponse } from '../types/api'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ACCESS_TOKEN_KEY = 'securedocs_access_token'
const CSRF_TOKEN_KEY = 'securedocs_csrf_token'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = message
  }
}

export class AuthExpiredError extends ApiError {
  constructor(message = 'Your session has expired. Please log in again.') {
    super(message, 401)
    this.name = 'AuthExpiredError'
  }
}

export function getAccessToken(): string | null {
  try {
    return sessionStorage.getItem(ACCESS_TOKEN_KEY) || localStorage.getItem(ACCESS_TOKEN_KEY)
  } catch {
    return null
  }
}

export function getCsrfToken(): string | null {
  try {
    // 1. Try reading from cookie
    if (typeof document !== 'undefined' && document.cookie) {
      const match = document.cookie.match(/(?:^|;\s*)securedocs_csrf_token=([^;]+)/)
      if (match) {
        return decodeURIComponent(match[1])
      }
    }
    // 2. Fallback to session storage
    return sessionStorage.getItem(CSRF_TOKEN_KEY)
  } catch {
    return null
  }
}

export function setTokens(accessToken: string, csrfToken?: string | null, remember = false): void {
  try {
    const storage = remember ? localStorage : sessionStorage
    storage.setItem(ACCESS_TOKEN_KEY, accessToken)
    if (csrfToken) {
      sessionStorage.setItem(CSRF_TOKEN_KEY, csrfToken)
    }
  } catch {
    // Storage access may be restricted
  }
}

export function clearTokens(): void {
  try {
    sessionStorage.removeItem(ACCESS_TOKEN_KEY)
    sessionStorage.removeItem(CSRF_TOKEN_KEY)
    localStorage.removeItem(ACCESS_TOKEN_KEY)
  } catch {
    // Ignore cleanup errors
  }
}

let isRefreshing = false
let refreshPromise: Promise<string | null> | null = null

export async function refreshAccessToken(): Promise<string | null> {
  if (isRefreshing && refreshPromise) {
    return refreshPromise
  }

  isRefreshing = true
  refreshPromise = (async () => {
    try {
      const csrfToken = getCsrfToken()
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      }
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers,
      })

      if (!response.ok) {
        clearTokens()
        return null
      }

      const data = (await response.json()) as TokenResponse
      setTokens(data.access_token, data.csrf_token)
      return data.access_token
    } catch {
      clearTokens()
      return null
    } finally {
      isRefreshing = false
      refreshPromise = null
    }
  })()

  return refreshPromise
}

export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`
  const headers = new Headers(options.headers || {})

  const token = getAccessToken()
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  // Attach CSRF token on state-changing auth calls if available
  if (endpoint.includes('/auth/logout') || endpoint.includes('/auth/refresh')) {
    const csrfToken = getCsrfToken()
    if (csrfToken && !headers.has('X-CSRF-Token')) {
      headers.set('X-CSRF-Token', csrfToken)
    }
  }

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const fetchOptions: RequestInit = {
    ...options,
    credentials: 'include',
    headers,
  }

  let response: Response
  try {
    response = await fetch(url, fetchOptions)
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Network error'
    throw new ApiError(`Network connection error: ${message}`, 0)
  }

  // Handle 401 Unauthorized with single token refresh retry
  if (response.status === 401 && !endpoint.includes('/auth/login') && !endpoint.includes('/auth/refresh')) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      headers.set('Authorization', `Bearer ${newToken}`)
      try {
        response = await fetch(url, { ...fetchOptions, headers })
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Network error'
        throw new ApiError(`Network connection error: ${message}`, 0)
      }
    } else {
      throw new AuthExpiredError()
    }
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const errJson = await response.json()
      if (errJson && typeof errJson.detail === 'string') {
        detail = errJson.detail
      } else if (errJson && Array.isArray(errJson.detail)) {
        // FastAPI validation errors
        detail = errJson.detail.map((e: { msg?: string }) => e.msg || 'Validation error').join(', ')
      }
    } catch {
      // Non-JSON error body
    }

    if (response.status === 401) {
      throw new AuthExpiredError(detail)
    }

    throw new ApiError(detail, response.status)
  }

  return response.json() as Promise<T>
}
