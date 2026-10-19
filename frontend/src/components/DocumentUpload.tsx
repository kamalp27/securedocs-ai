import { useState, useRef, type FC, type FormEvent, type ChangeEvent, type DragEvent } from 'react'
import { uploadDocument, MAX_FILE_SIZE_BYTES, SUPPORTED_EXTENSIONS } from '../api/documents'
import { ApiError, AuthExpiredError } from '../api/client'
import type { DocumentItem } from '../types/api'

interface DocumentUploadProps {
  onUploadSuccess: (doc: DocumentItem) => void
  onAuthExpired: () => void
}

export const DocumentUpload: FC<DocumentUploadProps> = ({
  onUploadSuccess,
  onAuthExpired,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [classification, setClassification] = useState('internal')
  const [isUploading, setIsUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const validateAndSetFile = (file: File) => {
    setErrorMessage(null)
    setSuccessMessage(null)

    // Check file extension
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!SUPPORTED_EXTENSIONS.includes(ext)) {
      setErrorMessage(
        `Unsupported file type "${ext}". Supported formats: ${SUPPORTED_EXTENSIONS.join(', ')}.`
      )
      setSelectedFile(null)
      return false
    }

    // Check file size
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setErrorMessage(
        `File "${file.name}" (${formatFileSize(file.size)}) exceeds the maximum allowed limit of 25 MB.`
      )
      setSelectedFile(null)
      return false
    }

    if (file.size === 0) {
      setErrorMessage(`File "${file.name}" is empty (0 bytes). Please upload a valid document.`)
      setSelectedFile(null)
      return false
    }

    setSelectedFile(file)
    return true
  }

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0])
    }
  }

  const handleDrag = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0])
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!selectedFile || isUploading) return

    setIsUploading(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      const doc = await uploadDocument(selectedFile, classification)
      setSuccessMessage(
        `Successfully uploaded "${doc.original_filename}" (${doc.chunk_count} chunk${
          doc.chunk_count === 1 ? '' : 's'
        } indexed).`
      )
      setSelectedFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      onUploadSuccess(doc)
    } catch (err: unknown) {
      if (err instanceof AuthExpiredError) {
        setErrorMessage('Session expired. Please log in again.')
        onAuthExpired()
      } else if (err instanceof ApiError) {
        setErrorMessage(err.detail)
      } else {
        const msg = err instanceof Error ? err.message : 'Upload failed'
        setErrorMessage(msg)
      }
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <section
      data-testid="document-upload-card"
      style={{
        backgroundColor: 'var(--bg, #fff)',
        border: '1px solid var(--border, #e5e4e7)',
        borderRadius: '12px',
        padding: '24px',
        boxShadow: 'var(--shadow)',
        marginBottom: '24px',
        textAlign: 'left',
      }}
    >
      <h2 style={{ fontSize: '1.25rem', margin: '0 0 6px 0', color: 'var(--text-h, #08060d)' }}>
        Upload Protected Document
      </h2>
      <p style={{ fontSize: '0.875rem', color: 'var(--text, #6b6375)', margin: '0 0 16px 0' }}>
        Uploaded files are validated, chunked, and embedded into isolated vector storage.
        Supported formats: <strong>PDF, DOCX, TXT, MD</strong> (Max: 25 MB).
      </p>

      {/* Success notification banner */}
      {successMessage && (
        <div
          data-testid="upload-success-banner"
          style={{
            padding: '10px 14px',
            backgroundColor: 'rgba(34, 197, 94, 0.12)',
            border: '1px solid rgba(34, 197, 94, 0.3)',
            borderRadius: '6px',
            color: '#15803d',
            fontSize: '0.875rem',
            marginBottom: '14px',
          }}
        >
          {successMessage}
        </div>
      )}

      {/* Error notification banner */}
      {errorMessage && (
        <div
          data-testid="upload-error-banner"
          style={{
            padding: '10px 14px',
            backgroundColor: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '6px',
            color: '#b91c1c',
            fontSize: '0.875rem',
            marginBottom: '14px',
          }}
        >
          {errorMessage}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        {/* Drag-and-drop dropzone */}
        <div
          data-testid="upload-dropzone"
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: `2px dashed ${dragActive ? 'var(--accent, #aa3bff)' : 'var(--border, #e5e4e7)'}`,
            borderRadius: '8px',
            padding: '28px 16px',
            textAlign: 'center',
            backgroundColor: dragActive ? 'var(--accent-bg, rgba(170, 59, 255, 0.08))' : 'var(--code-bg, #f4f3ec)',
            cursor: 'pointer',
            transition: 'border-color 0.2s, background-color 0.2s',
            marginBottom: '16px',
          }}
        >
          <input
            ref={fileInputRef}
            data-testid="file-picker-input"
            type="file"
            accept=".pdf,.docx,.txt,.md"
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />

          <div style={{ fontSize: '2rem', marginBottom: '8px' }}>📄</div>
          {selectedFile ? (
            <div>
              <p style={{ fontWeight: 600, color: 'var(--text-h, #08060d)', margin: '0 0 4px 0' }}>
                {selectedFile.name}
              </p>
              <p style={{ fontSize: '0.8rem', color: 'var(--text, #6b6375)', margin: 0 }}>
                Size: {formatFileSize(selectedFile.size)} • Click to choose a different file
              </p>
            </div>
          ) : (
            <div>
              <p style={{ fontWeight: 500, color: 'var(--text-h, #08060d)', margin: '0 0 4px 0' }}>
                Drag and drop your document here, or <span style={{ color: 'var(--accent, #aa3bff)', textDecoration: 'underline' }}>browse</span>
              </p>
              <p style={{ fontSize: '0.8rem', color: 'var(--text, #6b6375)', margin: 0 }}>
                PDF, DOCX, TXT, MD up to 25 MB
              </p>
            </div>
          )}
        </div>

        {/* Classification selector & Submit button */}
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label
              htmlFor="classification-select"
              style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-h, #08060d)' }}
            >
              Classification:
            </label>
            <select
              id="classification-select"
              data-testid="classification-select"
              value={classification}
              onChange={(e) => setClassification(e.target.value)}
              disabled={isUploading}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                border: '1px solid var(--border, #e5e4e7)',
                backgroundColor: 'var(--bg, #fff)',
                color: 'var(--text-h, #08060d)',
                fontSize: '0.875rem',
              }}
            >
              <option value="public">Public</option>
              <option value="internal">Internal</option>
              <option value="confidential">Confidential</option>
              <option value="restricted">Restricted</option>
            </select>
          </div>

          <button
            type="submit"
            data-testid="upload-submit-button"
            disabled={!selectedFile || isUploading}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: !selectedFile || isUploading ? 'var(--border, #e5e4e7)' : 'var(--accent, #aa3bff)',
              color: !selectedFile || isUploading ? 'var(--text, #6b6375)' : '#fff',
              fontSize: '0.875rem',
              fontWeight: 500,
              cursor: !selectedFile || isUploading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'background-color 0.2s',
            }}
          >
            {isUploading ? (
              <>
                <span
                  style={{
                    display: 'inline-block',
                    width: '14px',
                    height: '14px',
                    border: '2px solid rgba(255,255,255,0.3)',
                    borderTopColor: '#fff',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                  }}
                />
                Uploading & Ingesting...
              </>
            ) : (
              'Upload Document'
            )}
          </button>
        </div>
      </form>
    </section>
  )
}
