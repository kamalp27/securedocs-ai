import { useState, useEffect } from 'react'
import { getCurrentUser, logoutUser } from './api/auth'
import { clearTokens, getAccessToken } from './api/client'
import { LoginForm } from './components/LoginForm'
import { QAChat } from './components/QAChat'
import { DocumentManager } from './components/DocumentManager'
import type { User } from './types/api'

export function App() {
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [initializing, setInitializing] = useState(true)
  const [activeTab, setActiveTab] = useState<'documents' | 'qa'>('documents')
  const [initialQAQuestion, setInitialQAQuestion] = useState<string>('')

  useEffect(() => {
    async function verifyAuth() {
      const token = getAccessToken()
      if (token) {
        try {
          const user = await getCurrentUser()
          setCurrentUser(user)
        } catch {
          clearTokens()
          setCurrentUser(null)
        }
      }
      setInitializing(false)
    }

    verifyAuth()
  }, [])

  const handleLogout = async () => {
    await logoutUser()
    setCurrentUser(null)
  }

  const handleAuthExpired = () => {
    clearTokens()
    setCurrentUser(null)
  }

  if (initializing) {
    return (
      <div
        data-testid="app-initializing"
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          color: 'var(--text, #6b6375)',
        }}
      >
        Initializing SecureDocs AI...
      </div>
    )
  }

  if (!currentUser) {
    return (
      <main style={{ padding: '16px', minHeight: '100vh', boxSizing: 'border-box' }}>
        <LoginForm onLoginSuccess={(user) => setCurrentUser(user)} />
      </main>
    )
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Application Navigation Bar */}
      <header
        data-testid="app-header-nav"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 24px',
          borderBottom: '1px solid var(--border, #e5e4e7)',
          backgroundColor: 'var(--bg, #fff)',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        {/* Brand and Tab Selectors */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <span style={{ fontWeight: 700, fontSize: '1.15rem', color: 'var(--text-h, #08060d)' }}>
            SecureDocs AI
          </span>

          <nav style={{ display: 'flex', gap: '8px' }}>
            <button
              type="button"
              data-testid="tab-documents"
              onClick={() => setActiveTab('documents')}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                border: '1px solid',
                borderColor: activeTab === 'documents' ? 'var(--accent, #aa3bff)' : 'transparent',
                backgroundColor:
                  activeTab === 'documents'
                    ? 'var(--accent-bg, rgba(170, 59, 255, 0.1))'
                    : 'transparent',
                color: activeTab === 'documents' ? 'var(--accent, #aa3bff)' : 'var(--text, #6b6375)',
                fontWeight: activeTab === 'documents' ? 600 : 400,
                fontSize: '0.875rem',
                cursor: 'pointer',
                transition: 'all 0.15s ease-in-out',
              }}
            >
              📄 Documents
            </button>

            <button
              type="button"
              data-testid="tab-qa"
              onClick={() => setActiveTab('qa')}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                border: '1px solid',
                borderColor: activeTab === 'qa' ? 'var(--accent, #aa3bff)' : 'transparent',
                backgroundColor:
                  activeTab === 'qa' ? 'var(--accent-bg, rgba(170, 59, 255, 0.1))' : 'transparent',
                color: activeTab === 'qa' ? 'var(--accent, #aa3bff)' : 'var(--text, #6b6375)',
                fontWeight: activeTab === 'qa' ? 600 : 400,
                fontSize: '0.875rem',
                cursor: 'pointer',
                transition: 'all 0.15s ease-in-out',
              }}
            >
              💬 Grounded Q&A
            </button>
          </nav>
        </div>

        {/* User Identity & Logout */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ textAlign: 'right', fontSize: '0.85rem' }}>
            <span style={{ fontWeight: 600, color: 'var(--text-h, #08060d)', display: 'block' }}>
              {currentUser.email}
            </span>
            <span
              style={{
                textTransform: 'uppercase',
                fontSize: '0.7rem',
                letterSpacing: '0.5px',
                backgroundColor: 'var(--accent-bg, rgba(170, 59, 255, 0.1))',
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
            data-testid="app-logout-button"
            onClick={handleLogout}
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

      {/* Main Tab Content */}
      <main style={{ padding: '24px 16px', flex: 1, boxSizing: 'border-box' }}>
        {activeTab === 'documents' ? (
          <DocumentManager
            currentUser={currentUser}
            onNavigateToQA={(doc) => {
              if (doc) {
                setInitialQAQuestion(`What key information does ${doc.original_filename} cover?`)
              }
              setActiveTab('qa')
            }}
            onAuthExpired={handleAuthExpired}
          />
        ) : (
          <QAChat
            currentUser={currentUser}
            initialQuestion={initialQAQuestion}
            onLogout={handleLogout}
            onAuthExpired={handleAuthExpired}
            onNavigateToDocuments={() => setActiveTab('documents')}
          />
        )}
      </main>
    </div>
  )
}

export default App
