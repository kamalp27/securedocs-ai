import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DocumentUpload } from '../DocumentUpload'
import * as docApi from '../../api/documents'
import type { DocumentItem } from '../../types/api'

describe('DocumentUpload Component', () => {
  const onUploadSuccess = vi.fn()
  const onAuthExpired = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders upload card with file picker, dropzone, and disabled submit button', () => {
    render(<DocumentUpload onUploadSuccess={onUploadSuccess} onAuthExpired={onAuthExpired} />)

    expect(screen.getByTestId('document-upload-card')).toBeInTheDocument()
    expect(screen.getByTestId('upload-dropzone')).toBeInTheDocument()
    expect(screen.getByTestId('classification-select')).toBeInTheDocument()

    const submitBtn = screen.getByTestId('upload-submit-button')
    expect(submitBtn).toBeDisabled()
  })

  it('enables submit button when valid file is selected', () => {
    render(<DocumentUpload onUploadSuccess={onUploadSuccess} onAuthExpired={onAuthExpired} />)

    const file = new File(['valid content'], 'report.pdf', { type: 'application/pdf' })
    const input = screen.getByTestId('file-picker-input')

    fireEvent.change(input, { target: { files: [file] } })

    expect(screen.getByText('report.pdf')).toBeInTheDocument()
    const submitBtn = screen.getByTestId('upload-submit-button')
    expect(submitBtn).not.toBeDisabled()
  })

  it('rejects unsupported file formats with error banner and disables submit', () => {
    render(<DocumentUpload onUploadSuccess={onUploadSuccess} onAuthExpired={onAuthExpired} />)

    const invalidFile = new File(['binary'], 'virus.exe', { type: 'application/x-msdownload' })
    const input = screen.getByTestId('file-picker-input')

    fireEvent.change(input, { target: { files: [invalidFile] } })

    const errorBanner = screen.getByTestId('upload-error-banner')
    expect(errorBanner).toHaveTextContent(/unsupported file type/i)
    expect(screen.getByTestId('upload-submit-button')).toBeDisabled()
  })

  it('rejects oversized files exceeding 25 MB with error banner', () => {
    render(<DocumentUpload onUploadSuccess={onUploadSuccess} onAuthExpired={onAuthExpired} />)

    const oversizedFile = new File(['big'], 'large.pdf', { type: 'application/pdf' })
    Object.defineProperty(oversizedFile, 'size', { value: 30 * 1024 * 1024 }) // 30 MB

    const input = screen.getByTestId('file-picker-input')
    fireEvent.change(input, { target: { files: [oversizedFile] } })

    const errorBanner = screen.getByTestId('upload-error-banner')
    expect(errorBanner).toHaveTextContent(/exceeds the maximum allowed limit/i)
    expect(screen.getByTestId('upload-submit-button')).toBeDisabled()
  })

  it('handles successful upload, calls onUploadSuccess and displays success message', async () => {
    const mockDoc: DocumentItem = {
      id: 'doc-uuid-1',
      title: 'manual.docx',
      original_filename: 'manual.docx',
      mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      file_size_bytes: 5000,
      sha256_checksum: 'a'.repeat(64),
      classification: 'internal',
      status: 'indexed',
      created_at: '2026-10-19T10:00:00Z',
      updated_at: '2026-10-19T10:00:00Z',
      chunk_count: 4,
    }

    vi.spyOn(docApi, 'uploadDocument').mockResolvedValue(mockDoc)

    render(<DocumentUpload onUploadSuccess={onUploadSuccess} onAuthExpired={onAuthExpired} />)

    const file = new File(['word content'], 'manual.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })
    const input = screen.getByTestId('file-picker-input')
    fireEvent.change(input, { target: { files: [file] } })

    const submitBtn = screen.getByTestId('upload-submit-button')
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByTestId('upload-success-banner')).toHaveTextContent(/successfully uploaded/i)
      expect(onUploadSuccess).toHaveBeenCalledWith(mockDoc)
    })
  })

  it('handles server upload errors and displays detail banner', async () => {
    vi.spyOn(docApi, 'uploadDocument').mockRejectedValue(
      new Error('Password-protected PDF files cannot be processed')
    )

    render(<DocumentUpload onUploadSuccess={onUploadSuccess} onAuthExpired={onAuthExpired} />)

    const file = new File(['encrypted pdf'], 'secret.pdf', { type: 'application/pdf' })
    const input = screen.getByTestId('file-picker-input')
    fireEvent.change(input, { target: { files: [file] } })

    const submitBtn = screen.getByTestId('upload-submit-button')
    fireEvent.click(submitBtn)

    await waitFor(() => {
      const errorBanner = screen.getByTestId('upload-error-banner')
      expect(errorBanner).toHaveTextContent(/password-protected/i)
    })
  })
})
