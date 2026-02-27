import { colors, fonts } from '@styles/theme';

interface FormulaBlockProps {
  formula: string;
  label?: string;
}

const FormulaBlock = ({ formula, label }: FormulaBlockProps) => (
  <div style={{ marginBottom: 12 }}>
    {label && (
      <div style={{ color: colors.text.tertiary, fontSize: 12, marginBottom: 4 }}>{label}</div>
    )}
    <pre style={{
      background: colors.backgrounds.tertiary,
      border: `1px solid ${colors.backgrounds.border}`,
      borderRadius: 6,
      padding: '12px 16px',
      color: colors.brand.primary,
      fontFamily: fonts.mono,
      fontSize: 13,
      lineHeight: 1.6,
      overflowX: 'auto',
      margin: 0,
      whiteSpace: 'pre-wrap',
    }}>
      {formula}
    </pre>
  </div>
);

export default FormulaBlock;
