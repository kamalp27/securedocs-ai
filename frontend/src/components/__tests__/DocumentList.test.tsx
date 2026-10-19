import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DocumentList } from '../DocumentList'
import * as docApi from '../../api/documents'
import type { DocumentItem } from '../../types/api'

describe('DocumentList Component', () => {
  const mockDocuments: DocumentItem[] = [
    {
      id: 'doc-1',
      title: 'Company Bylaws.pdf',
      original_filename: 'Company Bylaws.pdf',
      mime_type: 'application/pdf',
      file_size_bytes: 204800, // 200 KB
      sha256_checksum: '1'.repeat(64),
      classification: 'internal',
      status: 'indexed',
      created_at: '2026-10-19T10:00:00Z',
      updated_at: '2026-10-19T10:00:00Z',
      chunk_count: 5,
    },
    {
      id: 'doc-2',
      title: 'Financial Q3.xlsx',
      original_filename: 'Financial Q3.txt',
      mime_type: 'text/plain',
      file_size_bytes: 10240, // 10 KB
      sha256_checksum: '2'.repeat(64),
      classification: 'confidential',
      status: 'failed',
      created_at: '2026-10-19T11:00:00Z',
      updated_at: '2026-10-19T11:00:00Z',
      chunk_count: 0,
    },
  ]

  const onRefresh = vi.fn()
  const onDeleteDoc = vi.fn().mockResolvedValue(undefined)
  const onAskQuestionAboutDoc = vi.fn()
  const onAuthExpired = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders document list with items, metadata, and chunk counts', () => {
    render(
      <DocumentList
        documents={mockDocuments}
        loading={false}
        error={null}
        onRefresh={onRefresh}
        onDeleteDoc={onDeleteDoc}
        onAskQuestionAboutDoc={onAskQuestionAboutDoc}
        onAuthExpired={onAuthExpired}
      />
    )

    expect(screen.getByTestId('document-table')).toBeInTheDocument()
    expect(screen.getByText('Company Bylaws.pdf')).toBeInTheDocument()
    expect(screen.getByText('Financial Q3.txt')).toBeInTheDocument()
    expect(screen.getByText('200.0 KB')).toBeInTheDocument()
  })

  it('filters documents in real-time when typing in search input', () => {
    render(
      <DocumentList
        documents={mockDocuments}
        loading={false}
        error={null}
        onRefresh={onRefresh}
        onDeleteDoc={onDeleteDoc}
        onAskQuestionAboutDoc={onAskQuestionAboutDoc}
        onAuthExpired={onAuthExpired}
      />
    )

    const searchInput = screen.getByTestId('document-search-input')
    fireEvent.change(searchInput, { target: { value: 'Bylaws' } })

    expect(screen.getByText('Company Bylaws.pdf')).toBeInTheDocument()
    expect(screen.queryByText('Financial Q3.txt')).not.toBeInTheDocument()
  })

  it('filters documents by status using status selector', () => {
    render(
      <DocumentList
        documents={mockDocuments}
        loading={false}
        error={null}
        onRefresh={onRefresh}
        onDeleteDoc={onDeleteDoc}
        onAskQuestionAboutDoc={onAskQuestionAboutDoc}
        onAuthExpired={onAuthExpired}
      />
    )

    const statusFilter = screen.getByTestId('document-status-filter')
    fireEvent.change(statusFilter, { target: { value: 'failed' } })

    expect(screen.queryByText('Company Bylaws.pdf')).not.toBeInTheDocument()
    expect(screen.getByText('Financial Q3.txt')).toBeInTheDocument()
  })

  it('triggers downloadDocument when download button is clicked', async () => {
    const downloadSpy = vi.spyOn(docApi, 'downloadDocument').mockResolvedValue(undefined)

    render(
      <DocumentList
        documents={mockDocuments}
        loading={false}
        error={null}
        onRefresh={onRefresh}
        onDeleteDoc={onDeleteDoc}
        onAskQuestionAboutDoc={onAskQuestionAboutDoc}
        onAuthExpired={onAuthExpired}
      />
    )

    const downloadBtn = screen.getByTestId('download-button-doc-1')
    fireEvent.click(downloadBtn)

    await waitFor(() => {
      expect(downloadSpy).toHaveBeenCalledWith('doc-1', 'Company Bylaws.pdf')
    })
  })

  it('opens confirmation modal on delete click and invokes onDeleteDoc on confirmation', async () => {
    render(
      <DocumentList
        documents={mockDocuments}
        loading={false}
        error={null}
        onRefresh={onRefresh}
        onDeleteDoc={onDeleteDoc}
        onAskQuestionAboutDoc={onAskQuestionAboutDoc}
        onAuthExpired={onAuthExpired}
      />
    )

    const deleteBtn = screen.getByTestId('delete-button-doc-1')
    fireEvent.click(deleteBtn)

    // Modal dialog must appear
    expect(screen.getByTestId('delete-confirmation-dialog')).toBeInTheDocument()
    expect(screen.getByText(/Confirm Document Deletion/i)).toBeInTheDocument()

    // Clicking confirm delete calls handler
    const confirmBtn = screen.getByTestId('confirm-delete-button')
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(onDeleteDoc).toHaveBeenCalledWith('doc-1')
      expect(screen.queryByTestId('delete-confirmation-dialog')).not.toBeInTheDocument()
    })
  })

  it('cancels deletion when cancel button is clicked in confirmation dialog', () => {
    render(
      <DocumentList
        documents={mockDocuments}
        loading={false}
        error={null}
        onRefresh={onRefresh}
        onDeleteDoc={onDeleteDoc}
        onAskQuestionAboutDoc={onAskQuestionAboutDoc}
        onAuthExpired={onAuthExpired}
      />
    )

    const deleteBtn = screen.getByTestId('delete-button-doc-1')
    fireEvent.click(deleteBtn)

    const cancelBtn = screen.getByTestId('cancel-delete-button')
    fireEvent.click(cancelBtn)

    expect(screen.queryByTestId('delete-confirmation-dialog')).not.toBeInTheDocument()
    expect(onDeleteDoc).not.toHaveBeenCalled()
  })

  it('renders empty state when no documents are provided', () => {
    render(
      <DocumentList
        documents={[]}
        loading={false}
        error={null}
        onRefresh={onRefresh}
        onDeleteDoc={onDeleteDoc}
        onAskQuestionAboutDoc={onAskQuestionAboutDoc}
        onAuthExpired={onAuthExpired}
      />
    )

    expect(screen.getByTestId('documents-empty-state')).toBeInTheDocument()
  })

  it('renders error state with retry button when error occurs', () => {
    render(
      <DocumentList
        documents={[]}
        loading={false}
        error="Network connection failure"
        onRefresh={onRefresh}
        onDeleteDoc={onDeleteDoc}
        onAskQuestionAboutDoc={onAskQuestionAboutDoc}
        onAuthExpired={onAuthExpired}
      />
    )

    expect(screen.getByTestId('documents-error-state')).toHaveTextContent(/Network connection failure/i)
    const retryBtn = screen.getByTestId('retry-fetch-documents-button')
    fireEvent.click(retryBtn)
    expect(onRefresh).toHaveBeenCalled()
  })
})
