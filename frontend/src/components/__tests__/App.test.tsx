import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { App } from '../../App'
import * as authApi from '../../api/auth'
import * as clientApi from '../../api/client'
import * as docApi from '../../api/documents'
import type { User } from '../../types/api'

describe('App Component Navigation & Lifecycle', () => {
  const mockUser: User = {
    id: 'user-uuid-1',
    email: 'analyst@securedocs.io',
    role: 'analyst',
    is_active: true,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(docApi, 'listDocuments').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
      total_pages: 0,
    })
  })

  it('renders login form when no active access token exists', async () => {
    vi.spyOn(clientApi, 'getAccessToken').mockReturnValue(null)

    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('login-container')).toBeInTheDocument()
      expect(screen.queryByTestId('app-header-nav')).not.toBeInTheDocument()
    })
  })

  it('renders app navigation and Document Vault by default when authenticated', async () => {
    vi.spyOn(clientApi, 'getAccessToken').mockReturnValue('mock.access.token')
    vi.spyOn(authApi, 'getCurrentUser').mockResolvedValue(mockUser)

    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('app-header-nav')).toBeInTheDocument()
      expect(screen.getByTestId('tab-documents')).toBeInTheDocument()
      expect(screen.getByTestId('tab-qa')).toBeInTheDocument()
      expect(screen.getByTestId('document-manager-container')).toBeInTheDocument()
    })
  })

  it('switches between Document Vault and Grounded Q&A tabs', async () => {
    vi.spyOn(clientApi, 'getAccessToken').mockReturnValue('mock.access.token')
    vi.spyOn(authApi, 'getCurrentUser').mockResolvedValue(mockUser)

    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('tab-qa')).toBeInTheDocument()
    })

    // Click on Grounded Q&A tab
    fireEvent.click(screen.getByTestId('tab-qa'))

    await waitFor(() => {
      expect(screen.getByTestId('qa-chat-container')).toBeInTheDocument()
      expect(screen.queryByTestId('document-manager-container')).not.toBeInTheDocument()
    })

    // Click back on Documents tab
    fireEvent.click(screen.getByTestId('tab-documents'))

    await waitFor(() => {
      expect(screen.getByTestId('document-manager-container')).toBeInTheDocument()
      expect(screen.queryByTestId('qa-chat-container')).not.toBeInTheDocument()
    })
  })

  it('clicking sign out logs the user out and renders login form', async () => {
    vi.spyOn(clientApi, 'getAccessToken').mockReturnValue('mock.access.token')
    vi.spyOn(authApi, 'getCurrentUser').mockResolvedValue(mockUser)
    const logoutSpy = vi.spyOn(authApi, 'logoutUser').mockResolvedValue(undefined)

    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('app-logout-button')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('app-logout-button'))

    await waitFor(() => {
      expect(logoutSpy).toHaveBeenCalled()
      expect(screen.getByTestId('login-container')).toBeInTheDocument()
    })
  })
})
