import type { FC } from 'react'

interface ProviderSelectorProps {
  value: string
  onChange: (provider: string) => void
  disabled?: boolean
}

export const ProviderSelector: FC<ProviderSelectorProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        fontSize: '0.85rem',
      }}
    >
      <label
        htmlFor="provider-select"
        style={{
          fontWeight: 500,
          color: 'var(--text, #6b6375)',
        }}
      >
        Generator Provider:
      </label>
      <select
        id="provider-select"
        data-testid="provider-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        style={{
          padding: '4px 10px',
          borderRadius: '6px',
          border: '1px solid var(--border, #e5e4e7)',
          backgroundColor: 'var(--bg, #fff)',
          color: 'var(--text-h, #08060d)',
          fontSize: '0.85rem',
          outline: 'none',
          cursor: disabled ? 'not-allowed' : 'pointer',
        }}
      >
        <option value="">Backend Default (Extractive Baseline)</option>
        <option value="deterministic_extractive">Deterministic Extractive</option>
        <option value="ollama">Ollama Local LLM (Optional)</option>
        <option value="mock">Mock Generator (Testing/Dev)</option>
      </select>
    </div>
  )
}
