/**
 * Authentication API service for user login, logout, and profile loading.
 */

import { apiFetch, clearTokens, getCsrfToken, setTokens } from './client'
import type { TokenResponse, User } from '../types/api'

export async function loginUser(email: string, password: string): Promise<User> {
  const tokenData = await apiFetch<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })

  setTokens(tokenData.access_token, tokenData.csrf_token)

  // Fetch authenticated user profile
  return getCurrentUser()
}

export async function getCurrentUser(): Promise<User> {
  return apiFetch<User>('/api/v1/auth/me', {
    method: 'GET',
  })
}

export async function logoutUser(): Promise<void> {
  try {
    const csrfToken = getCsrfToken()
    await apiFetch<void>('/api/v1/auth/logout', {
      method: 'POST',
      headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
    })
  } catch {
    // Ignore backend logout errors during local cleanup
  } finally {
    clearTokens()
  }
}
