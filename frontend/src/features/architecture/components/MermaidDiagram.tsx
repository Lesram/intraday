import { useEffect, useRef, useState, useId } from 'react';
import mermaid from 'mermaid';
import { colors } from '@styles/theme';

let initialized = false;

function initMermaid() {
  if (initialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    themeVariables: {
      primaryColor: colors.brand.primary,
      mainBkg: colors.backgrounds.secondary,
      nodeBorder: colors.brand.primary,
      nodeTextColor: colors.text.primary,
      lineColor: colors.text.tertiary,
      secondaryColor: colors.backgrounds.tertiary,
      tertiaryColor: colors.backgrounds.secondary,
      primaryTextColor: colors.text.primary,
      secondaryTextColor: colors.text.secondary,
      titleColor: colors.text.primary,
      edgeLabelBackground: colors.backgrounds.tertiary,
      clusterBkg: colors.backgrounds.tertiary,
      clusterBorder: colors.backgrounds.border,
    },
    flowchart: { curve: 'monotoneX', padding: 15 },
    sequence: { mirrorActors: false },
  });
  initialized = true;
}

interface MermaidDiagramProps {
  definition: string;
  onNodeClick?: (nodeId: string) => void;
}

const MermaidDiagram = ({ definition, onNodeClick }: MermaidDiagramProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const reactId = useId();
  const stableId = `mermaid-${reactId.replace(/:/g, '')}`;

  useEffect(() => {
    let cancelled = false;
    const render = async () => {
      initMermaid();
      try {
        const { svg } = await mermaid.render(stableId, definition.trim());
        if (cancelled || !containerRef.current) return;
        containerRef.current.innerHTML = svg;
        setError(null);

        if (onNodeClick) {
          containerRef.current.querySelectorAll('[id^="flowchart-"] .node, [id^="stateDiagram-"] .node').forEach((node) => {
            (node as HTMLElement).style.cursor = 'pointer';
            node.addEventListener('click', () => {
              const id = node.id || node.getAttribute('data-id') || '';
              onNodeClick(id);
            });
          });
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    };
    render();
    return () => { cancelled = true; };
  }, [definition, stableId, onNodeClick]);

  if (error) {
    return (
      <pre style={{
        background: colors.backgrounds.tertiary,
        color: colors.semantic.warning,
        padding: 16,
        borderRadius: 6,
        overflowX: 'auto',
        fontSize: 12,
      }}>
        {`Diagram render error:\n${error}\n\n${definition}`}
      </pre>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{ overflowX: 'auto', padding: '8px 0' }}
    />
  );
};

export default MermaidDiagram;
