import { useState, useRef, useEffect, type FC, type FormEvent, type KeyboardEvent } from 'react'
import { askQuestion } from '../api/qa'
import { logoutUser } from '../api/auth'
import { AuthExpiredError } from '../api/client'
import { CitationCard } from './CitationCard'
import { ProviderSelector } from './ProviderSelector'
import type { ChatMessage, User } from '../types/api'

interface QAChatProps {
  currentUser: User
  onLogout: () => void
  onAuthExpired: () => void
  initialQuestion?: string
  onNavigateToDocuments?: () => void
}

const SAMPLE_PROMPTS = [
  'What is the policy on encryption keys?',
  'When is the annual compliance review conducted?',
  'What are the disaster recovery guidelines?',
]

export const QAChat: FC<QAChatProps> = ({
  currentUser,
  onLogout,
  onAuthExpired,
  initialQuestion,
  onNavigateToDocuments,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputQuestion, setInputQuestion] = useState(initialQuestion || '')
  const [selectedProvider, setSelectedProvider] = useState('')
  const [loading, setLoading] = useState(false)
  const [errorBanner, setErrorBanner] = useState<string | null>(null)
  const [isSessionExpired, setIsSessionExpired] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading])

  const handleLogoutClick = async () => {
    await logoutUser()
    onLogout()
  }

  const handleSubmit = async (e?: FormEvent) => {
    if (e) e.preventDefault()

    const cleanQuestion = inputQuestion.trim()
    if (!cleanQuestion || loading) return

    setErrorBanner(null)
    setIsSessionExpired(false)

    // Add user message to conversation
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: cleanQuestion,
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInputQuestion('')
    setLoading(true)

    try {
      const response = await askQuestion({
        question: cleanQuestion,
        top_k: 5,
        provider: selectedProvider || null,
      })

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.answer,
        timestamp: new Date(),
        citations: response.citations,
        insufficient_evidence: response.insufficient_evidence,
        provider: response.provider,
        retrieved_chunk_count: response.retrieved_chunk_count,
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (err: unknown) {
      if (err instanceof AuthExpiredError) {
        setIsSessionExpired(true)
        setErrorBanner('Your session has expired. Please sign in again.')
        onAuthExpired()
      } else {
        const errorMsg =
          err instanceof Error
            ? err.message
            : 'An unexpected error occurred while communicating with the server.'
        setErrorBanner(errorMsg)

        // Record error assistant message in chat log
        const errorAssistantMessage: ChatMessage = {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: 'Unable to retrieve answer due to a server or connection error.',
          timestamp: new Date(),
          error: errorMsg,
        }
        setMessages((prev) => [...prev, errorAssistantMessage])
      }
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleSamplePromptClick = (prompt: string) => {
    setInputQuestion(prompt)
    textareaRef.current?.focus()
  }

  return (
    <div
      data-testid="qa-chat-container"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '92vh',
        width: '100%',
        maxWidth: '960px',
        margin: '0 auto',
        backgroundColor: 'var(--bg, #fff)',
        borderRadius: '12px',
        border: '1px solid var(--border, #e5e4e7)',
        overflow: 'hidden',
        boxShadow: 'var(--shadow, 0 10px 15px -3px rgba(0, 0, 0, 0.1))',
      }}
    >
      {/* Top Header */}
      <header
        style={{
          padding: '14px 20px',
          borderBottom: '1px solid var(--border, #e5e4e7)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: 'var(--bg, #fff)',
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: '1.2rem', color: 'var(--text-h, #08060d)' }}>
            SecureDocs AI Q&amp;A
          </h2>
          <span
            style={{
              fontSize: '0.8rem',
              color: 'var(--text, #6b6375)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: '#10b981',
                display: 'inline-block',
              }}
            />
            Access-Controlled Grounded RAG
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {onNavigateToDocuments && (
            <button
              type="button"
              data-testid="nav-documents-button"
              onClick={onNavigateToDocuments}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                border: '1px solid var(--border, #e5e4e7)',
                backgroundColor: 'transparent',
                color: 'var(--text-h, #08060d)',
                fontSize: '0.85rem',
                cursor: 'pointer',
              }}
            >
              ← Manage Documents
            </button>
          )}

          <div style={{ textAlign: 'right', fontSize: '0.85rem' }}>
            <span style={{ fontWeight: 600, color: 'var(--text-h, #08060d)', display: 'block' }}>
              {currentUser.email}
            </span>
            <span
              style={{
                textTransform: 'uppercase',
                fontSize: '0.7rem',
                letterSpacing: '0.5px',
                backgroundColor: 'rgba(170, 59, 255, 0.1)',
                color: 'var(--accent, #aa3bff)',
                padding: '2px 6px',
                borderRadius: '4px',
              }}
            >
              {currentUser.role}
            </span>
          </div>

          <button
            type="button"
            data-testid="logout-button"
            onClick={handleLogoutClick}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid var(--border, #e5e4e7)',
              backgroundColor: 'transparent',
              color: 'var(--text, #6b6375)',
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Error Alert Banner */}
      {errorBanner && (
        <div
          data-testid="error-alert-banner"
          style={{
            padding: '10px 16px',
            backgroundColor: 'rgba(239, 68, 68, 0.12)',
            borderBottom: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#b91c1c',
            fontSize: '0.875rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{errorBanner}</span>
          {isSessionExpired ? (
            <button
              type="button"
              onClick={onAuthExpired}
              style={{
                backgroundColor: '#b91c1c',
                color: '#fff',
                border: 'none',
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '0.8rem',
                cursor: 'pointer',
              }}
            >
              Re-Login
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setErrorBanner(null)}
              style={{
                background: 'none',
                border: 'none',
                color: '#b91c1c',
                cursor: 'pointer',
                fontWeight: 700,
              }}
            >
              ✕
            </button>
          )}
        </div>
      )}

      {/* Chat Messages Body */}
      <div
        data-testid="messages-viewport"
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        {messages.length === 0 && (
          <div
            data-testid="empty-chat-welcome"
            style={{
              margin: 'auto',
              maxWidth: '560px',
              textAlign: 'center',
              padding: '24px',
            }}
          >
            <h3 style={{ margin: '0 0 10px 0', color: 'var(--text-h, #08060d)' }}>
              Ask questions about your documents
            </h3>
            <p style={{ color: 'var(--text, #6b6375)', fontSize: '0.9rem', marginBottom: '20px' }}>
              Every answer is synthesized strictly from documents you are authorized to view.
              Sources are verified and cited with exact document filenames and page numbers.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text, #6b6375)' }}>
                Try asking:
              </span>
              {SAMPLE_PROMPTS.map((prompt, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSamplePromptClick(prompt)}
                  style={{
                    padding: '10px 14px',
                    borderRadius: '8px',
                    border: '1px solid var(--border, #e5e4e7)',
                    backgroundColor: 'var(--bg, #fff)',
                    color: 'var(--text-h, #08060d)',
                    textAlign: 'left',
                    fontSize: '0.875rem',
                    cursor: 'pointer',
                  }}
                >
                  &ldquo;{prompt}&rdquo;
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            data-testid={`message-${msg.role}`}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            <div
              style={{
                maxWidth: '82%',
                padding: '14px 18px',
                borderRadius: '12px',
                backgroundColor:
                  msg.role === 'user'
                    ? 'var(--accent, #aa3bff)'
                    : 'var(--code-bg, #f4f3ec)',
                color: msg.role === 'user' ? '#fff' : 'var(--text-h, #08060d)',
                border:
                  msg.role === 'assistant'
                    ? '1px solid var(--border, #e5e4e7)'
                    : 'none',
                textAlign: 'left',
                wordBreak: 'break-word',
              }}
            >
              {/* Provider Badge for Assistant Responses */}
              {msg.role === 'assistant' && msg.provider && (
                <div style={{ marginBottom: '8px' }}>
                  <span
                    data-testid="provider-badge"
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: '4px',
                      backgroundColor:
                        msg.provider === 'ollama'
                          ? 'rgba(59, 130, 246, 0.15)'
                          : 'rgba(170, 59, 255, 0.12)',
                      color:
                        msg.provider === 'ollama' ? '#2563eb' : 'var(--accent, #aa3bff)',
                    }}
                  >
                    {msg.provider === 'ollama'
                      ? 'Generated by Ollama Local LLM'
                      : msg.provider === 'deterministic_extractive'
                      ? 'Extracted from Authorized Documents'
                      : `Provider: ${msg.provider}`}
                  </span>
                </div>
              )}

              {/* Insufficient Evidence Warning Banner */}
              {msg.role === 'assistant' && msg.insufficient_evidence && (
                <div
                  data-testid="insufficient-evidence-banner"
                  style={{
                    backgroundColor: 'rgba(245, 158, 11, 0.15)',
                    border: '1px solid rgba(245, 158, 11, 0.4)',
                    color: '#b45309',
                    borderRadius: '6px',
                    padding: '8px 12px',
                    marginBottom: '10px',
                    fontSize: '0.85rem',
                    fontWeight: 500,
                  }}
                >
                  ⚠️ Insufficient Evidence: The authorized documents do not provide direct evidence to confirm this answer.
                </div>
              )}

              {/* Safe Text Rendering (No dangerouslySetInnerHTML) */}
              <p
                style={{
                  margin: 0,
                  fontSize: '0.95rem',
                  lineHeight: '1.5',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {msg.content}
              </p>

              {/* Citations Section */}
              {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                <div style={{ marginTop: '14px', paddingTop: '10px', borderTop: '1px solid rgba(0, 0, 0, 0.08)' }}>
                  <div
                    style={{
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      color: 'var(--text, #6b6375)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      marginBottom: '4px',
                    }}
                  >
                    Verified Citations ({msg.citations.length})
                  </div>
                  {msg.citations.map((citation, citIdx) => (
                    <CitationCard key={citation.chunk_id || citIdx} citation={citation} index={citIdx} />
                  ))}
                </div>
              )}
            </div>

            <span
              style={{
                fontSize: '0.7rem',
                color: 'var(--text, #6b6375)',
                marginTop: '4px',
                paddingInline: '4px',
              }}
            >
              {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        ))}

        {/* Loading Spinner Indicator */}
        {loading && (
          <div
            data-testid="loading-indicator"
            style={{
              alignSelf: 'flex-start',
              padding: '12px 18px',
              borderRadius: '12px',
              backgroundColor: 'var(--code-bg, #f4f3ec)',
              border: '1px solid var(--border, #e5e4e7)',
              fontSize: '0.9rem',
              color: 'var(--text, #6b6375)',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <div
              style={{
                width: '14px',
                height: '14px',
                borderRadius: '50%',
                border: '2px solid var(--accent, #aa3bff)',
                borderTopColor: 'transparent',
                animation: 'spin 1s linear infinite',
              }}
            />
            Searching authorized documents and generating grounded answer...
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form Toolbar */}
      <footer
        style={{
          padding: '14px 20px',
          borderTop: '1px solid var(--border, #e5e4e7)',
          backgroundColor: 'var(--bg, #fff)',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '10px',
          }}
        >
          <ProviderSelector
            value={selectedProvider}
            onChange={setSelectedProvider}
            disabled={loading}
          />

          <span
            data-testid="char-counter"
            style={{
              fontSize: '0.75rem',
              color: inputQuestion.length > 900 ? '#ef4444' : 'var(--text, #6b6375)',
            }}
          >
            {inputQuestion.length} / 1000
          </span>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '10px', alignItems: 'flex-end' }}>
          <textarea
            ref={textareaRef}
            data-testid="question-input"
            value={inputQuestion}
            onChange={(e) => setInputQuestion(e.target.value.slice(0, 1000))}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your authorized documents... (Enter to send, Shift+Enter for newline)"
            rows={2}
            disabled={loading}
            style={{
              flex: 1,
              padding: '10px 14px',
              borderRadius: '8px',
              border: '1px solid var(--border, #e5e4e7)',
              backgroundColor: 'var(--bg, #fff)',
              color: 'var(--text-h, #08060d)',
              fontSize: '0.95rem',
              resize: 'none',
              outline: 'none',
              fontFamily: 'inherit',
            }}
          />

          <button
            type="submit"
            data-testid="submit-question-button"
            disabled={loading || !inputQuestion.trim()}
            style={{
              padding: '12px 20px',
              borderRadius: '8px',
              backgroundColor: 'var(--accent, #aa3bff)',
              color: '#fff',
              fontWeight: 600,
              fontSize: '0.95rem',
              border: 'none',
              cursor: loading || !inputQuestion.trim() ? 'not-allowed' : 'pointer',
              opacity: loading || !inputQuestion.trim() ? 0.5 : 1,
              height: '52px',
            }}
          >
            {loading ? 'Asking...' : 'Ask'}
          </button>
        </form>
      </footer>
    </div>
  )
}
