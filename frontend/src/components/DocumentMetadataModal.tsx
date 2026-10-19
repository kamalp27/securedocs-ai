import { useEffect, useState, type FC } from 'react'
import { getDocument } from '../api/documents'
import type { DocumentDetail } from '../types/api'

interface DocumentMetadataModalProps {
  documentId: string
  onClose: () => void
}

export const DocumentMetadataModal: FC<DocumentMetadataModalProps> = ({
  documentId,
  onClose,
}) => {
  const [docDetail, setDocDetail] = useState<DocumentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true
    async function fetchDetail() {
      setLoading(true)
      setError(null)
      try {
        const detail = await getDocument(documentId)
        if (isMounted) setDocDetail(detail)
      } catch (err: unknown) {
        if (isMounted) {
          const msg = err instanceof Error ? err.message : 'Failed to load document metadata'
          setError(msg)
        }
      } finally {
        if (isMounted) setLoading(false)
      }
    }

    fetchDetail()

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      isMounted = false
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [documentId, onClose])

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div
      data-testid="document-metadata-modal-overlay"
      onClick={onClose}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '16px',
        boxSizing: 'border-box',
      }}
    >
      <div
        data-testid="document-metadata-modal"
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: 'var(--bg, #fff)',
          border: '1px solid var(--border, #e5e4e7)',
          borderRadius: '12px',
          width: '700px',
          maxWidth: '100%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: 'var(--shadow)',
          overflow: 'hidden',
          textAlign: 'left',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid var(--border, #e5e4e7)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <h3 style={{ margin: 0, fontSize: '1.15rem', color: 'var(--text-h, #08060d)' }}>
            Document Metadata & Preview
          </h3>
          <button
            type="button"
            data-testid="close-modal-button"
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'none',
              border: 'none',
              fontSize: '1.25rem',
              cursor: 'pointer',
              color: 'var(--text, #6b6375)',
            }}
          >
            ✕
          </button>
        </div>

        {/* Content body */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
          {loading && (
            <div data-testid="metadata-loading" style={{ textAlign: 'center', padding: '32px' }}>
              Loading document metadata...
            </div>
          )}

          {error && (
            <div
              data-testid="metadata-error"
              style={{
                padding: '12px',
                backgroundColor: 'rgba(239, 68, 68, 0.12)',
                borderRadius: '6px',
                color: '#b91c1c',
                fontSize: '0.875rem',
              }}
            >
              {error}
            </div>
          )}

          {docDetail && (
            <div>
              {/* Key metadata grid */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                  gap: '12px',
                  marginBottom: '20px',
                }}
              >
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text, #6b6375)', display: 'block' }}>
                    Filename
                  </span>
                  <strong style={{ fontSize: '0.9rem', color: 'var(--text-h, #08060d)' }}>
                    {docDetail.original_filename}
                  </strong>
                </div>

                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text, #6b6375)', display: 'block' }}>
                    Classification
                  </span>
                  <span
                    style={{
                      display: 'inline-block',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      backgroundColor: 'var(--accent-bg, rgba(170, 59, 255, 0.1))',
                      color: 'var(--accent, #aa3bff)',
                    }}
                  >
                    {docDetail.classification}
                  </span>
                </div>

                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text, #6b6375)', display: 'block' }}>
                    File Size
                  </span>
                  <span style={{ fontSize: '0.9rem', color: 'var(--text-h, #08060d)' }}>
                    {formatFileSize(docDetail.file_size_bytes)}
                  </span>
                </div>

                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text, #6b6375)', display: 'block' }}>
                    MIME Type
                  </span>
                  <code style={{ fontSize: '0.75rem' }}>{docDetail.mime_type}</code>
                </div>

                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text, #6b6375)', display: 'block' }}>
                    Status
                  </span>
                  <span
                    style={{
                      fontWeight: 600,
                      fontSize: '0.8rem',
                      color:
                        docDetail.status === 'indexed'
                          ? '#15803d'
                          : docDetail.status === 'failed'
                          ? '#b91c1c'
                          : '#b45309',
                    }}
                  >
                    {docDetail.status.toUpperCase()}
                  </span>
                </div>

                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text, #6b6375)', display: 'block' }}>
                    Chunks Indexed
                  </span>
                  <span style={{ fontSize: '0.9rem', color: 'var(--text-h, #08060d)' }}>
                    {docDetail.chunk_count}
                  </span>
                </div>

                <div style={{ gridColumn: '1 / -1' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text, #6b6375)', display: 'block' }}>
                    SHA-256 Integrity Checksum
                  </span>
                  <code style={{ fontSize: '0.75rem', wordBreak: 'break-all' }}>
                    {docDetail.sha256_checksum}
                  </code>
                </div>
              </div>

              {/* Chunk Snippets Preview */}
              <h4 style={{ margin: '16px 0 8px 0', fontSize: '0.95rem', color: 'var(--text-h, #08060d)' }}>
                Indexed Chunks Preview ({docDetail.chunks.length})
              </h4>
              {docDetail.chunks.length === 0 ? (
                <p style={{ fontSize: '0.85rem', color: 'var(--text, #6b6375)' }}>
                  No parsed chunks available for this document.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '250px', overflowY: 'auto' }}>
                  {docDetail.chunks.map((chunk) => (
                    <div
                      key={chunk.id}
                      style={{
                        padding: '10px',
                        borderRadius: '6px',
                        backgroundColor: 'var(--code-bg, #f4f3ec)',
                        border: '1px solid var(--border, #e5e4e7)',
                        fontSize: '0.8rem',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          marginBottom: '4px',
                          color: 'var(--text, #6b6375)',
                          fontSize: '0.75rem',
                        }}
                      >
                        <span>Chunk #{chunk.chunk_index + 1}</span>
                        <span>{chunk.token_count} tokens</span>
                      </div>
                      <p style={{ margin: 0, color: 'var(--text-h, #08060d)', whiteSpace: 'pre-wrap' }}>
                        {chunk.content.length > 200 ? chunk.content.slice(0, 200) + '...' : chunk.content}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '12px 20px',
            borderTop: '1px solid var(--border, #e5e4e7)',
            display: 'flex',
            justifyContent: 'flex-end',
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '6px 16px',
              borderRadius: '6px',
              border: '1px solid var(--border, #e5e4e7)',
              backgroundColor: 'transparent',
              color: 'var(--text, #6b6375)',
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
