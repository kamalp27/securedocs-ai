import { useState, useMemo, type FC } from 'react'
import { downloadDocument } from '../api/documents'
import { ApiError, AuthExpiredError } from '../api/client'
import { DocumentMetadataModal } from './DocumentMetadataModal'
import type { DocumentItem } from '../types/api'

interface DocumentListProps {
  documents: DocumentItem[]
  loading: boolean
  error: string | null
  onRefresh: () => void
  onDeleteDoc: (docId: string) => Promise<void>
  onAskQuestionAboutDoc: (doc: DocumentItem) => void
  onAuthExpired: () => void
}

export const DocumentList: FC<DocumentListProps> = ({
  documents,
  loading,
  error,
  onRefresh,
  onDeleteDoc,
  onAskQuestionAboutDoc,
  onAuthExpired,
}) => {
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [previewDocId, setPreviewDocId] = useState<string | null>(null)
  const [deleteConfirmDoc, setDeleteConfirmDoc] = useState<DocumentItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (isoString: string): string => {
    try {
      return new Date(isoString).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    } catch {
      return isoString
    }
  }

  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      const matchesSearch =
        doc.original_filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
        doc.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        doc.classification.toLowerCase().includes(searchTerm.toLowerCase())

      const matchesStatus =
        statusFilter === 'all' || doc.status.toLowerCase() === statusFilter.toLowerCase()

      return matchesSearch && matchesStatus
    })
  }, [documents, searchTerm, statusFilter])

  const handleDownload = async (doc: DocumentItem) => {
    setActionError(null)
    try {
      await downloadDocument(doc.id, doc.original_filename)
    } catch (err: unknown) {
      if (err instanceof AuthExpiredError) {
        onAuthExpired()
      } else if (err instanceof ApiError) {
        setActionError(`Download failed: ${err.detail}`)
      } else {
        const msg = err instanceof Error ? err.message : 'Download failed'
        setActionError(msg)
      }
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteConfirmDoc || isDeleting) return
    setIsDeleting(true)
    setActionError(null)
    try {
      await onDeleteDoc(deleteConfirmDoc.id)
      setDeleteConfirmDoc(null)
    } catch (err: unknown) {
      if (err instanceof AuthExpiredError) {
        onAuthExpired()
      } else if (err instanceof ApiError) {
        setActionError(`Delete failed: ${err.detail}`)
      } else {
        const msg = err instanceof Error ? err.message : 'Delete failed'
        setActionError(msg)
      }
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <section
      data-testid="document-list-card"
      style={{
        backgroundColor: 'var(--bg, #fff)',
        border: '1px solid var(--border, #e5e4e7)',
        borderRadius: '12px',
        padding: '24px',
        boxShadow: 'var(--shadow)',
        textAlign: 'left',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          <h2 style={{ fontSize: '1.25rem', margin: '0 0 4px 0', color: 'var(--text-h, #08060d)' }}>
            Your Accessible Documents
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text, #6b6375)', margin: 0 }}>
            {documents.length} document{documents.length === 1 ? '' : 's'} registered in your isolated workspace.
          </p>
        </div>

        <button
          type="button"
          data-testid="refresh-documents-button"
          onClick={onRefresh}
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
          🔄 Refresh
        </button>
      </div>

      {/* Action error banner */}
      {actionError && (
        <div
          data-testid="document-action-error-banner"
          style={{
            padding: '10px 14px',
            backgroundColor: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '6px',
            color: '#b91c1c',
            fontSize: '0.875rem',
            marginBottom: '16px',
          }}
        >
          {actionError}
        </div>
      )}

      {/* Filter and search bar */}
      <div
        style={{
          display: 'flex',
          gap: '12px',
          marginBottom: '16px',
          flexWrap: 'wrap',
        }}
      >
        <input
          type="text"
          data-testid="document-search-input"
          placeholder="Filter by filename or classification..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{
            flex: '1 1 240px',
            padding: '8px 12px',
            borderRadius: '6px',
            border: '1px solid var(--border, #e5e4e7)',
            fontSize: '0.875rem',
            backgroundColor: 'var(--bg, #fff)',
            color: 'var(--text-h, #08060d)',
          }}
        />

        <select
          data-testid="document-status-filter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{
            padding: '8px 12px',
            borderRadius: '6px',
            border: '1px solid var(--border, #e5e4e7)',
            fontSize: '0.875rem',
            backgroundColor: 'var(--bg, #fff)',
            color: 'var(--text-h, #08060d)',
          }}
        >
          <option value="all">All Statuses</option>
          <option value="indexed">Indexed</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {/* Loading state */}
      {loading && (
        <div
          data-testid="documents-loading-state"
          style={{
            textAlign: 'center',
            padding: '36px 0',
            color: 'var(--text, #6b6375)',
            fontSize: '0.9rem',
          }}
        >
          Loading your documents...
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div
          data-testid="documents-error-state"
          style={{
            textAlign: 'center',
            padding: '24px',
            backgroundColor: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            borderRadius: '8px',
          }}
        >
          <p style={{ color: '#b91c1c', fontSize: '0.9rem', marginBottom: '12px' }}>
            Failed to load documents: {error}
          </p>
          <button
            type="button"
            data-testid="retry-fetch-documents-button"
            onClick={onRefresh}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: 'var(--accent, #aa3bff)',
              color: '#fff',
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty state: No documents uploaded */}
      {!loading && !error && documents.length === 0 && (
        <div
          data-testid="documents-empty-state"
          style={{
            textAlign: 'center',
            padding: '48px 16px',
            backgroundColor: 'var(--code-bg, #f4f3ec)',
            borderRadius: '8px',
            border: '1px dashed var(--border, #e5e4e7)',
          }}
        >
          <div style={{ fontSize: '2.5rem', marginBottom: '12px' }}>📂</div>
          <p style={{ fontWeight: 500, color: 'var(--text-h, #08060d)', marginBottom: '4px' }}>
            No documents in your vault yet
          </p>
          <p style={{ fontSize: '0.85rem', color: 'var(--text, #6b6375)' }}>
            Upload your first PDF, Word, or Markdown document above to enable search and grounded Q&A.
          </p>
        </div>
      )}

      {/* Empty state: No filter matches */}
      {!loading && !error && documents.length > 0 && filteredDocuments.length === 0 && (
        <div
          data-testid="documents-no-matches"
          style={{
            textAlign: 'center',
            padding: '32px 16px',
            color: 'var(--text, #6b6375)',
            fontSize: '0.875rem',
          }}
        >
          No documents matched &quot;{searchTerm}&quot;. Try adjusting your search query.
        </div>
      )}

      {/* Document table / card view */}
      {!loading && !error && filteredDocuments.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table
            data-testid="document-table"
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.875rem',
              textAlign: 'left',
            }}
          >
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border, #e5e4e7)', color: 'var(--text, #6b6375)' }}>
                <th style={{ padding: '10px 12px' }}>Document</th>
                <th style={{ padding: '10px 12px' }}>Classification</th>
                <th style={{ padding: '10px 12px' }}>Size</th>
                <th style={{ padding: '10px 12px' }}>Status</th>
                <th style={{ padding: '10px 12px' }}>Chunks</th>
                <th style={{ padding: '10px 12px' }}>Uploaded</th>
                <th style={{ padding: '10px 12px', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredDocuments.map((doc) => (
                <tr
                  key={doc.id}
                  data-testid={`document-row-${doc.id}`}
                  style={{
                    borderBottom: '1px solid var(--border, #e5e4e7)',
                    transition: 'background-color 0.15s',
                  }}
                >
                  <td style={{ padding: '12px', fontWeight: 500, color: 'var(--text-h, #08060d)' }}>
                    {doc.original_filename}
                  </td>
                  <td style={{ padding: '12px' }}>
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        backgroundColor: 'var(--accent-bg, rgba(170, 59, 255, 0.1))',
                        color: 'var(--accent, #aa3bff)',
                      }}
                    >
                      {doc.classification}
                    </span>
                  </td>
                  <td style={{ padding: '12px', color: 'var(--text, #6b6375)' }}>
                    {formatFileSize(doc.file_size_bytes)}
                  </td>
                  <td style={{ padding: '12px' }}>
                    <span
                      style={{
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        color:
                          doc.status === 'indexed'
                            ? '#15803d'
                            : doc.status === 'failed'
                            ? '#b91c1c'
                            : '#b45309',
                      }}
                    >
                      {doc.status === 'indexed' ? '✓ ' : ''}
                      {doc.status}
                    </span>
                  </td>
                  <td style={{ padding: '12px', color: 'var(--text, #6b6375)' }}>
                    {doc.chunk_count}
                  </td>
                  <td style={{ padding: '12px', color: 'var(--text, #6b6375)' }}>
                    {formatDate(doc.created_at)}
                  </td>
                  <td style={{ padding: '12px', textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', gap: '6px' }}>
                      <button
                        type="button"
                        data-testid={`download-button-${doc.id}`}
                        onClick={() => handleDownload(doc)}
                        title="Download Document"
                        style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          border: '1px solid var(--border, #e5e4e7)',
                          backgroundColor: 'var(--bg, #fff)',
                          cursor: 'pointer',
                          fontSize: '0.75rem',
                          color: 'var(--text-h, #08060d)',
                        }}
                      >
                        ⬇ Download
                      </button>

                      <button
                        type="button"
                        data-testid={`metadata-button-${doc.id}`}
                        onClick={() => setPreviewDocId(doc.id)}
                        title="View Metadata & Chunks"
                        style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          border: '1px solid var(--border, #e5e4e7)',
                          backgroundColor: 'var(--bg, #fff)',
                          cursor: 'pointer',
                          fontSize: '0.75rem',
                          color: 'var(--text-h, #08060d)',
                        }}
                      >
                        ℹ Info
                      </button>

                      <button
                        type="button"
                        data-testid={`ask-doc-button-${doc.id}`}
                        onClick={() => onAskQuestionAboutDoc(doc)}
                        title="Ask Questions About This Document"
                        style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          border: '1px solid var(--accent-border, rgba(170, 59, 255, 0.5))',
                          backgroundColor: 'var(--accent-bg, rgba(170, 59, 255, 0.08))',
                          color: 'var(--accent, #aa3bff)',
                          cursor: 'pointer',
                          fontSize: '0.75rem',
                          fontWeight: 500,
                        }}
                      >
                        💬 Ask AI
                      </button>

                      <button
                        type="button"
                        data-testid={`delete-button-${doc.id}`}
                        onClick={() => setDeleteConfirmDoc(doc)}
                        title="Delete Document"
                        style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          border: '1px solid rgba(239, 68, 68, 0.3)',
                          backgroundColor: 'transparent',
                          color: '#b91c1c',
                          cursor: 'pointer',
                          fontSize: '0.75rem',
                        }}
                      >
                        🗑 Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Document Metadata Modal */}
      {previewDocId && (
        <DocumentMetadataModal
          documentId={previewDocId}
          onClose={() => setPreviewDocId(null)}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirmDoc && (
        <div
          data-testid="delete-confirmation-modal-overlay"
          onClick={() => !isDeleting && setDeleteConfirmDoc(null)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '16px',
          }}
        >
          <div
            data-testid="delete-confirmation-dialog"
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: 'var(--bg, #fff)',
              border: '1px solid var(--border, #e5e4e7)',
              borderRadius: '12px',
              padding: '24px',
              maxWidth: '460px',
              width: '100%',
              boxShadow: 'var(--shadow)',
              textAlign: 'left',
            }}
          >
            <h3 style={{ margin: '0 0 10px 0', fontSize: '1.15rem', color: '#b91c1c' }}>
              Confirm Document Deletion
            </h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-h, #08060d)', margin: '0 0 16px 0' }}>
              Are you sure you want to permanently delete{' '}
              <strong>&quot;{deleteConfirmDoc.original_filename}&quot;</strong>?
            </p>
            <p style={{ fontSize: '0.8rem', color: 'var(--text, #6b6375)', margin: '0 0 20px 0' }}>
              This will irreversibly remove the file from storage and delete all {deleteConfirmDoc.chunk_count} chunk
              embeddings from semantic search indices.
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                type="button"
                data-testid="cancel-delete-button"
                disabled={isDeleting}
                onClick={() => setDeleteConfirmDoc(null)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '6px',
                  border: '1px solid var(--border, #e5e4e7)',
                  backgroundColor: 'transparent',
                  color: 'var(--text, #6b6375)',
                  cursor: isDeleting ? 'not-allowed' : 'pointer',
                  fontSize: '0.875rem',
                }}
              >
                Cancel
              </button>

              <button
                type="button"
                data-testid="confirm-delete-button"
                disabled={isDeleting}
                onClick={handleConfirmDelete}
                style={{
                  padding: '6px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: isDeleting ? 'var(--border, #e5e4e7)' : '#b91c1c',
                  color: '#fff',
                  cursor: isDeleting ? 'not-allowed' : 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: 500,
                }}
              >
                {isDeleting ? 'Deleting...' : 'Permanently Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
