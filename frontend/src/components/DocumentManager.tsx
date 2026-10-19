import { useState, useEffect, useCallback, type FC } from 'react'
import { listDocuments, deleteDocument } from '../api/documents'
import { ApiError, AuthExpiredError } from '../api/client'
import { DocumentUpload } from './DocumentUpload'
import { DocumentList } from './DocumentList'
import type { DocumentItem, User } from '../types/api'

interface DocumentManagerProps {
  currentUser: User
  onNavigateToQA: (doc?: DocumentItem) => void
  onAuthExpired: () => void
}

export const DocumentManager: FC<DocumentManagerProps> = ({
  onNavigateToQA,
  onAuthExpired,
}) => {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchDocs = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await listDocuments(1, 100)
      setDocuments(response.items)
    } catch (err: unknown) {
      if (err instanceof AuthExpiredError) {
        onAuthExpired()
      } else if (err instanceof ApiError) {
        setError(err.detail)
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to fetch documents'
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [onAuthExpired])

  useEffect(() => {
    let ignore = false

    async function initialLoad() {
      try {
        const response = await listDocuments(1, 100)
        if (!ignore) {
          setDocuments(response.items)
          setLoading(false)
        }
      } catch (err: unknown) {
        if (!ignore) {
          if (err instanceof AuthExpiredError) {
            onAuthExpired()
          } else if (err instanceof ApiError) {
            setError(err.detail)
          } else {
            const msg = err instanceof Error ? err.message : 'Failed to fetch documents'
            setError(msg)
          }
          setLoading(false)
        }
      }
    }

    initialLoad()
    return () => {
      ignore = true
    }
  }, [onAuthExpired])

  const handleUploadSuccess = (newDoc: DocumentItem) => {
    setDocuments((prev) => [newDoc, ...prev.filter((d) => d.id !== newDoc.id)])
  }

  const handleDeleteDocument = async (docId: string) => {
    await deleteDocument(docId)
    setDocuments((prev) => prev.filter((d) => d.id !== docId))
  }

  return (
    <div data-testid="document-manager-container" style={{ width: '100%', maxWidth: '1000px', margin: '0 auto' }}>
      {/* Upload Section */}
      <DocumentUpload
        onUploadSuccess={handleUploadSuccess}
        onAuthExpired={onAuthExpired}
      />

      {/* Document List Section */}
      <DocumentList
        documents={documents}
        loading={loading}
        error={error}
        onRefresh={fetchDocs}
        onDeleteDoc={handleDeleteDocument}
        onAskQuestionAboutDoc={onNavigateToQA}
        onAuthExpired={onAuthExpired}
      />
    </div>
  )
}
