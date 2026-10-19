import type { FC } from 'react'
import type { Citation } from '../types/api'

interface CitationCardProps {
  citation: Citation
  index: number
}

export const CitationCard: FC<CitationCardProps> = ({ citation, index }) => {
  return (
    <div
      data-testid={`citation-card-${index}`}
      className="citation-card"
      style={{
        backgroundColor: 'var(--code-bg, #f4f3ec)',
        border: '1px solid var(--border, #e5e4e7)',
        borderRadius: '8px',
        padding: '12px 14px',
        marginTop: '8px',
        textAlign: 'left',
        fontSize: '0.9rem',
        lineHeight: '1.4',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '6px',
          marginBottom: '6px',
        }}
      >
        <span
          style={{
            fontWeight: 600,
            color: 'var(--text-h, #08060d)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: '18px',
              height: '18px',
              borderRadius: '50%',
              backgroundColor: 'var(--accent, #aa3bff)',
              color: '#fff',
              textAlign: 'center',
              lineHeight: '18px',
              fontSize: '0.75rem',
              fontWeight: 700,
            }}
          >
            {index + 1}
          </span>
          {/* Plain text rendering prevents XSS */}
          {citation.original_filename}
        </span>

        <div style={{ display: 'flex', gap: '6px', fontSize: '0.8rem' }}>
          {citation.page_number !== null && citation.page_number !== undefined && (
            <span
              style={{
                backgroundColor: 'rgba(0, 0, 0, 0.06)',
                padding: '2px 8px',
                borderRadius: '4px',
                color: 'var(--text, #6b6375)',
              }}
            >
              Page {citation.page_number}
            </span>
          )}
          {citation.section && (
            <span
              style={{
                backgroundColor: 'rgba(0, 0, 0, 0.06)',
                padding: '2px 8px',
                borderRadius: '4px',
                color: 'var(--text, #6b6375)',
              }}
            >
              {citation.section}
            </span>
          )}
        </div>
      </div>

      {citation.quoted_snippet && (
        <blockquote
          style={{
            margin: '6px 0 0 0',
            paddingLeft: '10px',
            borderLeft: '3px solid var(--accent, #aa3bff)',
            fontStyle: 'italic',
            color: 'var(--text, #6b6375)',
            fontSize: '0.85rem',
            wordBreak: 'break-word',
          }}
        >
          {/* Strictly rendered as plain text */}
          &ldquo;{citation.quoted_snippet}&rdquo;
        </blockquote>
      )}
    </div>
  )
}
