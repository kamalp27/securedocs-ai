import { describe, expect, it, vi, beforeEach } from 'vitest'
import {
  listDocuments,
  getDocument,
  uploadDocument,
  downloadDocument,
  deleteDocument,
  MAX_FILE_SIZE_BYTES,
} from '../documents'
import { ApiError } from '../client'

describe('Document API Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('listDocuments fetches paginated documents with query params', async () => {
    const fakeListResponse = {
      items: [
        {
          id: 'doc-uuid-1',
          title: 'Q3 Security Policy',
          original_filename: 'security_q3.pdf',
          mime_type: 'application/pdf',
          file_size_bytes: 1048576,
          sha256_checksum: 'a'.repeat(64),
          classification: 'confidential',
          status: 'indexed',
          created_at: '2026-10-19T10:00:00Z',
          updated_at: '2026-10-19T10:00:00Z',
          chunk_count: 8,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    }

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(fakeListResponse), { status: 200 })
    )

    const result = await listDocuments(1, 20, 'indexed')
    expect(result.items.length).toBe(1)
    expect(result.items[0].original_filename).toBe('security_q3.pdf')

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/documents?page=1&page_size=20&status=indexed'),
      expect.objectContaining({ method: 'GET' })
    )
  })

  it('getDocument fetches document details and chunks', async () => {
    const fakeDetail = {
      id: 'doc-uuid-1',
      title: 'Q3 Security Policy',
      original_filename: 'security_q3.pdf',
      mime_type: 'application/pdf',
      file_size_bytes: 1048576,
      sha256_checksum: 'a'.repeat(64),
      classification: 'internal',
      status: 'indexed',
      created_at: '2026-10-19T10:00:00Z',
      updated_at: '2026-10-19T10:00:00Z',
      chunk_count: 1,
      chunks: [
        {
          id: 'chunk-1',
          chunk_index: 0,
          content: 'Section 1. Security Architecture.',
          token_count: 5,
        },
      ],
    }

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(fakeDetail), { status: 200 })
    )

    const detail = await getDocument('doc-uuid-1')
    expect(detail.id).toBe('doc-uuid-1')
    expect(detail.chunks.length).toBe(1)
    expect(detail.chunks[0].content).toContain('Security Architecture')
  })

  it('uploadDocument rejects oversized files before network submission', async () => {
    const oversizedFile = new File(['a'], 'oversized.pdf', { type: 'application/pdf' })
    Object.defineProperty(oversizedFile, 'size', { value: MAX_FILE_SIZE_BYTES + 1 })

    await expect(uploadDocument(oversizedFile, 'internal')).rejects.toThrow(ApiError)
  })

  it('uploadDocument sends multipart/form-data and returns DocumentItem', async () => {
    const validFile = new File(['Dummy content'], 'valid.txt', { type: 'text/plain' })
    const fakeUploadedDoc = {
      id: 'doc-uuid-2',
      title: 'valid.txt',
      original_filename: 'valid.txt',
      mime_type: 'text/plain',
      file_size_bytes: 13,
      sha256_checksum: 'b'.repeat(64),
      classification: 'internal',
      status: 'indexed',
      created_at: '2026-10-19T10:00:00Z',
      updated_at: '2026-10-19T10:00:00Z',
      chunk_count: 1,
    }

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(fakeUploadedDoc), { status: 201 })
    )

    const doc = await uploadDocument(validFile, 'internal')
    expect(doc.id).toBe('doc-uuid-2')
    expect(doc.original_filename).toBe('valid.txt')

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/documents/upload'),
      expect.objectContaining({
        method: 'POST',
        body: expect.any(FormData),
      })
    )
  })

  it('downloadDocument fetches binary blob and triggers link download', async () => {
    const fakeBlob = new Blob(['binary file data'], { type: 'application/pdf' })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(fakeBlob, { status: 200 })
    )

    const createObjectURLSpy = vi.fn().mockReturnValue('blob:http://localhost/fake-uuid')
    const revokeObjectURLSpy = vi.fn()
    window.URL.createObjectURL = createObjectURLSpy
    window.URL.revokeObjectURL = revokeObjectURLSpy

    await downloadDocument('doc-uuid-1', 'test_doc.pdf')

    expect(createObjectURLSpy).toHaveBeenCalled()
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:http://localhost/fake-uuid')
  })

  it('deleteDocument sends DELETE request to document endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ message: 'Deleted successfully' }), { status: 200 })
    )

    await deleteDocument('doc-uuid-1')

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/documents/doc-uuid-1'),
      expect.objectContaining({ method: 'DELETE' })
    )
  })
})
