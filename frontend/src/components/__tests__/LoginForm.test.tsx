import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { LoginForm } from '../LoginForm'
import * as authApi from '../../api/auth'

vi.mock('../../api/auth')

describe('LoginForm Component', () => {
  it('renders login form with empty default inputs', () => {
    render(<LoginForm onLoginSuccess={vi.fn()} />)
    expect(screen.getByTestId('login-container')).toBeInTheDocument()
    const emailInput = screen.getByTestId('login-email') as HTMLInputElement
    const passwordInput = screen.getByTestId('login-password') as HTMLInputElement
    expect(emailInput.value).toBe('')
    expect(passwordInput.value).toBe('')
    expect(screen.getByTestId('login-submit-button')).toBeInTheDocument()
    // Confirm no demo credentials or passwords in rendered DOM
    expect(screen.queryByText(/Demo Credentials/i)).not.toBeInTheDocument()
  })

  it('renders client error when submitting empty fields', () => {
    render(<LoginForm onLoginSuccess={vi.fn()} />)
    fireEvent.click(screen.getByTestId('login-submit-button'))
    expect(screen.getByTestId('login-error-alert')).toBeInTheDocument()
    expect(screen.getByText('Please provide both email and password.')).toBeInTheDocument()
    expect(authApi.loginUser).not.toHaveBeenCalled()
  })

  it('submits credentials and invokes onLoginSuccess', async () => {
    const mockUser = {
      id: 'u-1',
      email: 'user@securedocs.io',
      role: 'analyst',
      is_active: true,
    }
    vi.mocked(authApi.loginUser).mockResolvedValueOnce(mockUser)
    const onLoginSuccess = vi.fn()

    render(<LoginForm onLoginSuccess={onLoginSuccess} />)

    fireEvent.change(screen.getByTestId('login-email'), {
      target: { value: 'user@securedocs.io' },
    })
    fireEvent.change(screen.getByTestId('login-password'), {
      target: { value: 'TestPassword2026!' },
    })
    fireEvent.click(screen.getByTestId('login-submit-button'))

    await waitFor(() => {
      expect(authApi.loginUser).toHaveBeenCalledWith(
        'user@securedocs.io',
        'TestPassword2026!'
      )
      expect(onLoginSuccess).toHaveBeenCalledWith(mockUser)
    })
  })

  it('renders error alert on login failure', async () => {
    vi.mocked(authApi.loginUser).mockRejectedValueOnce(
      new Error('Incorrect email or password.')
    )

    render(<LoginForm onLoginSuccess={vi.fn()} />)

    fireEvent.change(screen.getByTestId('login-email'), {
      target: { value: 'user@securedocs.io' },
    })
    fireEvent.change(screen.getByTestId('login-password'), {
      target: { value: 'WrongPassword!' },
    })
    fireEvent.click(screen.getByTestId('login-submit-button'))

    await waitFor(() => {
      expect(screen.getByTestId('login-error-alert')).toBeInTheDocument()
      expect(
        screen.getByText('Incorrect email or password.')
      ).toBeInTheDocument()
    })
  })
})
