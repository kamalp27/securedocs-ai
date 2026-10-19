import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  apiFetch,
  AuthExpiredError,
  clearTokens,
  getAccessToken,
  refreshAccessToken,
  setTokens,
} from '../client'
import { loginUser, logoutUser } from '../auth'

describe('Frontend Cookie-based Authentication & API Client', () => {
  beforeEach(() => {
    clearTokens()
    vi.restoreAllMocks()
    // Reset document.cookie in test environment
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: '',
    })
  })

  it('loginUser stores access token in session and does not write refresh token to storage', async () => {
    const fakeTokenResponse = {
      access_token: 'valid.access.jwt',
      token_type: 'bearer',
      expires_in: 1800,
      csrf_token: 'csrf-secret-123',
    }
    const fakeUser = {
      id: 'user-uuid-1',
      email: 'analyst@securedocs.io',
      role: 'analyst',
      is_active: true,
    }

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.includes('/auth/login')) {
        return Promise.resolve(new Response(JSON.stringify(fakeTokenResponse), { status: 200 }))
      }
      if (url.includes('/auth/me')) {
        return Promise.resolve(new Response(JSON.stringify(fakeUser), { status: 200 }))
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`))
    })

    const user = await loginUser('analyst@securedocs.io', 'Password123!')

    expect(user.email).toBe('analyst@securedocs.io')
    expect(getAccessToken()).toBe('valid.access.jwt')

    // Verify refresh token is strictly absent from both sessionStorage and localStorage
    expect(sessionStorage.getItem('securedocs_refresh_token')).toBeNull()
    expect(localStorage.getItem('securedocs_refresh_token')).toBeNull()

    // Verify credentials: 'include' was sent
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/auth/login'),
      expect.objectContaining({ credentials: 'include' })
    )
  })

  it('refreshAccessToken sends credentials: "include" and X-CSRF-Token header without reading refresh token from storage', async () => {
    document.cookie = 'securedocs_csrf_token=csrf-cookie-val-999; path=/'
    setTokens('old.access.jwt', 'csrf-cookie-val-999')

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            access_token: 'new.rotated.jwt',
            token_type: 'bearer',
            expires_in: 1800,
            csrf_token: 'csrf-cookie-val-1000',
          }),
          { status: 200 }
        )
      )
    })

    const newAccessToken = await refreshAccessToken()

    expect(newAccessToken).toBe('new.rotated.jwt')
    expect(getAccessToken()).toBe('new.rotated.jwt')

    // Verify refresh request used credentials: 'include' and sent X-CSRF-Token
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/auth/refresh'),
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({
          'X-CSRF-Token': 'csrf-cookie-val-999',
        }),
      })
    )
  })

  it('refreshAccessToken clears access token and returns null on 401 refresh failure', async () => {
    setTokens('expired.access.jwt')

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Refresh token expired' }), { status: 401 })
    )

    const result = await refreshAccessToken()

    expect(result).toBeNull()
    expect(getAccessToken()).toBeNull()
  })

  it('logoutUser sends X-CSRF-Token and clears stored credentials', async () => {
    document.cookie = 'securedocs_csrf_token=csrf-token-abc; path=/'
    setTokens('active.access.jwt', 'csrf-token-abc')

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ message: 'Successfully logged out.' }), { status: 200 })
    )

    await logoutUser()

    expect(getAccessToken()).toBeNull()
    expect(fetchSpy).toHaveBeenCalled()
    const callArgs = fetchSpy.mock.calls[0]
    expect(String(callArgs[0])).toContain('/auth/logout')
    expect(callArgs[1]?.method).toBe('POST')
    expect(callArgs[1]?.credentials).toBe('include')

    const sentHeaders = callArgs[1]?.headers as Headers
    expect(sentHeaders.get('X-CSRF-Token')).toBe('csrf-token-abc')
  })

  it('apiFetch retries once upon receiving 401 and throws AuthExpiredError if refresh fails', async () => {
    setTokens('expired.access.jwt')

    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.includes('/auth/refresh')) {
        return Promise.resolve(new Response(JSON.stringify({ detail: 'Session expired' }), { status: 401 }))
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 }))
    })

    await expect(apiFetch('/api/v1/documents')).rejects.toThrow(AuthExpiredError)
  })
})
