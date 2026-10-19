import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { CitationCard } from '../CitationCard'
import type { Citation } from '../../types/api'

describe('CitationCard Component', () => {
  it('renders citation with page and section metadata', () => {
    const citation: Citation = {
      chunk_id: 'c1',
      document_id: 'd1',
      original_filename: 'compliance_manual.pdf',
      page_number: 12,
      section: 'Incident Response',
      quoted_snippet: 'Incidents must be triaged within 15 minutes of detection.',
    }

    render(<CitationCard citation={citation} index={0} />)

    expect(screen.getByTestId('citation-card-0')).toBeInTheDocument()
    expect(screen.getByText('compliance_manual.pdf')).toBeInTheDocument()
    expect(screen.getByText('Page 12')).toBeInTheDocument()
    expect(screen.getByText('Incident Response')).toBeInTheDocument()
    expect(
      screen.getByText(/Incidents must be triaged within 15 minutes of detection./)
    ).toBeInTheDocument()
  })

  it('renders citation safely when optional metadata is omitted', () => {
    const citation: Citation = {
      chunk_id: 'c2',
      document_id: 'd2',
      original_filename: 'readme.txt',
      quoted_snippet: null,
    }

    render(<CitationCard citation={citation} index={2} />)

    expect(screen.getByTestId('citation-card-2')).toBeInTheDocument()
    expect(screen.getByText('readme.txt')).toBeInTheDocument()
    expect(screen.queryByText(/Page/)).toBeNull()
  })
})
