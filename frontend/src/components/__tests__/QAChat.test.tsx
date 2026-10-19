import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QAChat } from '../QAChat'
import * as qaApi from '../../api/qa'
import * as authApi from '../../api/auth'
import { AuthExpiredError } from '../../api/client'
import type { QAResponse, User } from '../../types/api'

// Mock API modules
vi.mock('../../api/qa')
vi.mock('../../api/auth')

const mockUser: User = {
  id: 'user-123',
  email: 'analyst@securedocs.io',
  role: 'analyst',
  is_active: true,
}

describe('QAChat Component', () => {
  const mockOnLogout = vi.fn()
  const mockOnAuthExpired = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    // Mock scrollIntoView in jsdom
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
  })

  it('renders welcome screen and user status when empty', () => {
    render(
      <QAChat
        currentUser={mockUser}
        onLogout={mockOnLogout}
        onAuthExpired={mockOnAuthExpired}
      />
    )

    expect(screen.getByText('SecureDocs AI Q&A')).toBeInTheDocument()
    expect(screen.getByText('analyst@securedocs.io')).toBeInTheDocument()
    expect(screen.getByText('analyst')).toBeInTheDocument()
    expect(screen.getByTestId('empty-chat-welcome')).toBeInTheDocument()
    expect(screen.getByTestId('question-input')).toBeInTheDocument()
  })

  it('submits question and renders answer with verified citations', async () => {
    const mockResponse: QAResponse = {
      question: 'What is the encryption standard for backups?',
      answer: 'All customer backups are encrypted using AES-256.',
      citations: [
        {
          chunk_id: 'c1',
          document_id: 'd1',
          original_filename: 'security_policy.pdf',
          page_number: 3,
          section: 'Data Protection',
          quoted_snippet: 'backups are encrypted using AES-256',
        },
      ],
      insufficient_evidence: false,
      provider: 'deterministic_extractive',
      retrieved_chunk_count: 1,
      retrieved_chunks: [
        {
          chunk_id: 'c1',
          document_id: 'd1',
          original_filename: 'security_policy.pdf',
          similarity_score: 0.92,
          page_number: 3,
        },
      ],
    }

    vi.mocked(qaApi.askQuestion).mockResolvedValueOnce(mockResponse)

    render(
      <QAChat
        currentUser={mockUser}
        onLogout={mockOnLogout}
        onAuthExpired={mockOnAuthExpired}
      />
    )

    const input = screen.getByTestId('question-input')
    const submitBtn = screen.getByTestId('submit-question-button')

    fireEvent.change(input, {
      target: { value: 'What is the encryption standard for backups?' },
    })
    fireEvent.click(submitBtn)

    // User message should appear immediately
    expect(
      screen.getByText('What is the encryption standard for backups?')
    ).toBeInTheDocument()

    // Wait for assistant response to render
    await waitFor(() => {
      expect(
        screen.getByText('All customer backups are encrypted using AES-256.')
      ).toBeInTheDocument()
    })

    // Citation details should be rendered
    expect(screen.getByText('security_policy.pdf')).toBeInTheDocument()
    expect(screen.getByText('Page 3')).toBeInTheDocument()
    expect(screen.getByText('Data Protection')).toBeInTheDocument()
    expect(
      screen.getAllByText(/backups are encrypted using AES-256/).length
    ).toBeGreaterThanOrEqual(1)

    // Provider badge should reflect extraction
    expect(
      screen.getByText('Extracted from Authorized Documents')
    ).toBeInTheDocument()
  })

  it('renders insufficient evidence banner when backend declares insufficient evidence', async () => {
    const mockResponse: QAResponse = {
      question: 'What is the company policy on Martian colonization?',
      answer:
        'Insufficient evidence: I could not find sufficient evidence in your authorized documents.',
      citations: [],
      insufficient_evidence: true,
      provider: 'deterministic_extractive',
      retrieved_chunk_count: 0,
      retrieved_chunks: [],
    }

    vi.mocked(qaApi.askQuestion).mockResolvedValueOnce(mockResponse)

    render(
      <QAChat
        currentUser={mockUser}
        onLogout={mockOnLogout}
        onAuthExpired={mockOnAuthExpired}
      />
    )

    const input = screen.getByTestId('question-input')
    fireEvent.change(input, { target: { value: 'What is the Martian policy?' } })
    fireEvent.click(screen.getByTestId('submit-question-button'))

    await waitFor(() => {
      expect(
        screen.getByTestId('insufficient-evidence-banner')
      ).toBeInTheDocument()
    })

    expect(
      screen.getByText(/The authorized documents do not provide direct evidence/)
    ).toBeInTheDocument()
  })

  it('renders answers and snippets safely as text preventing XSS', async () => {
    const xssPayload = '<img src=x onerror=alert(1) /><script>evil()</script>'
    const mockResponse: QAResponse = {
      question: 'XSS test',
      answer: xssPayload,
      citations: [
        {
          chunk_id: 'c2',
          document_id: 'd2',
          original_filename: '<script>alert(filename)</script>.txt',
          page_number: 1,
          quoted_snippet: '<b onmouseover=evil()>quoted</b>',
        },
      ],
      insufficient_evidence: false,
      provider: 'deterministic_extractive',
      retrieved_chunk_count: 1,
      retrieved_chunks: [],
    }

    vi.mocked(qaApi.askQuestion).mockResolvedValueOnce(mockResponse)

    render(
      <QAChat
        currentUser={mockUser}
        onLogout={mockOnLogout}
        onAuthExpired={mockOnAuthExpired}
      />
    )

    const input = screen.getByTestId('question-input')
    fireEvent.change(input, { target: { value: 'XSS test' } })
    fireEvent.click(screen.getByTestId('submit-question-button'))

    await waitFor(() => {
      // The text must be rendered verbatim as text content, not as DOM elements
      expect(screen.getByText(xssPayload)).toBeInTheDocument()
    })

    // Ensure no script or img elements were injected
    expect(document.querySelector('script[src]')).toBeNull()
    expect(document.querySelector('img[src="x"]')).toBeNull()
  })

  it('handles server errors and renders error alert banner', async () => {
    vi.mocked(qaApi.askQuestion).mockRejectedValueOnce(
      new Error('Local LLM provider is currently unavailable.')
    )

    render(
      <QAChat
        currentUser={mockUser}
        onLogout={mockOnLogout}
        onAuthExpired={mockOnAuthExpired}
      />
    )

    const input = screen.getByTestId('question-input')
    fireEvent.change(input, { target: { value: 'Failing query' } })
    fireEvent.click(screen.getByTestId('submit-question-button'))

    await waitFor(() => {
      expect(screen.getByTestId('error-alert-banner')).toBeInTheDocument()
    })

    expect(
      screen.getByText('Local LLM provider is currently unavailable.')
    ).toBeInTheDocument()
  })

  it('triggers onAuthExpired callback when session expires (401)', async () => {
    vi.mocked(qaApi.askQuestion).mockRejectedValueOnce(
      new AuthExpiredError('Your session has expired.')
    )

    render(
      <QAChat
        currentUser={mockUser}
        onLogout={mockOnLogout}
        onAuthExpired={mockOnAuthExpired}
      />
    )

    const input = screen.getByTestId('question-input')
    fireEvent.change(input, { target: { value: 'Query with expired token' } })
    fireEvent.click(screen.getByTestId('submit-question-button'))

    await waitFor(() => {
      expect(mockOnAuthExpired).toHaveBeenCalledTimes(1)
    })
  })

  it('allows provider selection and transmits selected provider to API', async () => {
    const mockResponse: QAResponse = {
      question: 'Test with Ollama',
      answer: 'Answer generated by Ollama local model.',
      citations: [],
      insufficient_evidence: false,
      provider: 'ollama',
      retrieved_chunk_count: 1,
      retrieved_chunks: [],
    }

    vi.mocked(qaApi.askQuestion).mockResolvedValueOnce(mockResponse)

    render(
      <QAChat
        currentUser={mockUser}
        onLogout={mockOnLogout}
        onAuthExpired={mockOnAuthExpired}
      />
    )

    const providerSelect = screen.getByTestId('provider-select')
    fireEvent.change(providerSelect, { target: { value: 'ollama' } })

    const input = screen.getByTestId('question-input')
    fireEvent.change(input, { target: { value: 'Test with Ollama' } })
    fireEvent.click(screen.getByTestId('submit-question-button'))

    await waitFor(() => {
      expect(qaApi.askQuestion).toHaveBeenCalledWith({
        question: 'Test with Ollama',
        top_k: 5,
        provider: 'ollama',
      })
    })

    await waitFor(() => {
      expect(
        screen.getByText('Generated by Ollama Local LLM')
      ).toBeInTheDocument()
    })
  })

  it('calls logout API when clicking Sign Out button', async () => {
    vi.mocked(authApi.logoutUser).mockResolvedValueOnce()

    render(
      <QAChat
        currentUser={mockUser}
        onLogout={mockOnLogout}
        onAuthExpired={mockOnAuthExpired}
      />
    )

    const logoutBtn = screen.getByTestId('logout-button')
    fireEvent.click(logoutBtn)

    await waitFor(() => {
      expect(authApi.logoutUser).toHaveBeenCalledTimes(1)
      expect(mockOnLogout).toHaveBeenCalledTimes(1)
    })
  })
})
