import { useState, type FC, type FormEvent } from 'react'
import { loginUser } from '../api/auth'
import type { User } from '../types/api'

interface LoginFormProps {
  onLoginSuccess: (user: User) => void
}

export const LoginForm: FC<LoginFormProps> = ({ onLoginSuccess }) => {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) {
      setError('Please provide both email and password.')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const user = await loginUser(email.trim(), password)
      onLoginSuccess(user)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Authentication failed.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      data-testid="login-container"
      style={{
        maxWidth: '420px',
        margin: '60px auto',
        padding: '32px 28px',
        borderRadius: '12px',
        backgroundColor: 'var(--bg, #fff)',
        border: '1px solid var(--border, #e5e4e7)',
        boxShadow: 'var(--shadow, 0 10px 15px -3px rgba(0, 0, 0, 0.1))',
        textAlign: 'left',
      }}
    >
      <div style={{ textAlign: 'center', marginBottom: '24px' }}>
        <h2 style={{ margin: '0 0 8px 0', color: 'var(--text-h, #08060d)' }}>SecureDocs AI</h2>
        <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text, #6b6375)' }}>
          Sign in to access your authorized documents and grounded Q&A
        </p>
      </div>

      {error && (
        <div
          data-testid="login-error-alert"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#b91c1c',
            borderRadius: '6px',
            padding: '10px 12px',
            fontSize: '0.875rem',
            marginBottom: '16px',
          }}
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '16px' }}>
          <label
            htmlFor="login-email"
            style={{
              display: 'block',
              fontWeight: 500,
              fontSize: '0.875rem',
              marginBottom: '6px',
              color: 'var(--text-h, #08060d)',
            }}
          >
            Email Address
          </label>
          <input
            id="login-email"
            data-testid="login-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            style={{
              width: '100%',
              boxSizing: 'border-box',
              padding: '10px 12px',
              borderRadius: '6px',
              border: '1px solid var(--border, #e5e4e7)',
              backgroundColor: 'var(--bg, #fff)',
              color: 'var(--text-h, #08060d)',
              fontSize: '0.95rem',
            }}
          />
        </div>

        <div style={{ marginBottom: '20px' }}>
          <label
            htmlFor="login-password"
            style={{
              display: 'block',
              fontWeight: 500,
              fontSize: '0.875rem',
              marginBottom: '6px',
              color: 'var(--text-h, #08060d)',
            }}
          >
            Password
          </label>
          <input
            id="login-password"
            data-testid="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            style={{
              width: '100%',
              boxSizing: 'border-box',
              padding: '10px 12px',
              borderRadius: '6px',
              border: '1px solid var(--border, #e5e4e7)',
              backgroundColor: 'var(--bg, #fff)',
              color: 'var(--text-h, #08060d)',
              fontSize: '0.95rem',
            }}
          />
        </div>

        <button
          type="submit"
          data-testid="login-submit-button"
          disabled={loading}
          style={{
            width: '100%',
            padding: '12px',
            borderRadius: '6px',
            backgroundColor: 'var(--accent, #aa3bff)',
            color: '#fff',
            fontWeight: 600,
            fontSize: '0.95rem',
            border: 'none',
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? 'Authenticating...' : 'Sign In'}
        </button>
      </form>

      {import.meta.env.DEV && (
        <div
          data-testid="dev-helper-note"
          style={{
            marginTop: '20px',
            paddingTop: '16px',
            borderTop: '1px solid var(--border, #e5e4e7)',
            fontSize: '0.8rem',
            color: 'var(--text, #6b6375)',
          }}
        >
          <span>Development environment active</span>
        </div>
      )}
    </div>
  )
}
