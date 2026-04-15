import React from 'react';
import type { ManifestValidationResult } from '../../world/manifest_schema';

interface Props {
  result: ManifestValidationResult | null;
}

export function ValidationPanel({ result }: Props) {
  if (!result) return null;

  return (
    <div style={{ marginTop: 8 }}>
      {result.valid ? (
        <div style={validBox}>
          <span style={{ fontWeight: 700 }}>✓ Valid</span>
          {result.compiled_summary && (
            <span style={{ marginLeft: 8, color: '#555', fontSize: 11 }}>
              {result.compiled_summary}
            </span>
          )}
        </div>
      ) : (
        <div style={invalidBox}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>✗ Invalid — not applied</div>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {result.errors.map((e, i) => (
              <li key={i} style={{ marginBottom: 2 }}>{e}</li>
            ))}
          </ul>
        </div>
      )}
      {result.warnings.length > 0 && (
        <div style={warningBox}>
          <div style={{ fontWeight: 600, marginBottom: 2 }}>Warnings:</div>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {result.warnings.map((w, i) => (
              <li key={i} style={{ marginBottom: 1 }}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

const validBox: React.CSSProperties = {
  background: '#f0faf0',
  border: '1px solid #c3e6cb',
  borderRadius: 4,
  padding: '6px 10px',
  fontSize: 11,
  color: '#2d6a2d'
};

const invalidBox: React.CSSProperties = {
  background: '#fdf2f2',
  border: '1px solid #f5c6cb',
  borderRadius: 4,
  padding: '6px 10px',
  fontSize: 11,
  color: '#721c24'
};

const warningBox: React.CSSProperties = {
  background: '#fff8e1',
  border: '1px solid #ffe082',
  borderRadius: 4,
  padding: '6px 10px',
  fontSize: 11,
  color: '#856404',
  marginTop: 4
};
