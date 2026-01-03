/* Crow IDE Enhanced Markdown Renderer with KaTeX and Mermaid */
import { memo, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import mermaid from "mermaid";
import "katex/dist/katex.min.css";

// Initialize mermaid with dark theme
mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  themeVariables: {
    primaryColor: "#1f6feb",
    primaryTextColor: "#e6edf3",
    primaryBorderColor: "#30363d",
    lineColor: "#8b949e",
    secondaryColor: "#161b22",
    tertiaryColor: "#21262d",
    background: "#0d1117",
    mainBkg: "#161b22",
    nodeBorder: "#30363d",
    clusterBkg: "#21262d",
    titleColor: "#e6edf3",
    edgeLabelBackground: "#161b22",
  },
  fontFamily: "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace",
});

interface MermaidBlockProps {
  code: string;
}

const MermaidBlock = memo<MermaidBlockProps>(({ code }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const renderDiagram = async () => {
      if (!code.trim()) return;

      try {
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg } = await mermaid.render(id, code.trim());
        setSvg(svg);
        setError(null);
      } catch (err) {
        console.error("Mermaid render error:", err);
        setError(err instanceof Error ? err.message : "Failed to render diagram");
      }
    };

    renderDiagram();
  }, [code]);

  if (error) {
    return (
      <div className="border border-red-700 bg-red-900/20 rounded p-3 my-2">
        <div className="text-xs text-red-400 mb-1">Mermaid Error:</div>
        <pre className="text-xs text-red-300 whitespace-pre-wrap">{error}</pre>
        <details className="mt-2">
          <summary className="text-xs text-gray-400 cursor-pointer">Show code</summary>
          <pre className="text-xs text-gray-300 mt-1 whitespace-pre-wrap">{code}</pre>
        </details>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="border border-gray-700 rounded p-3 my-2 animate-pulse">
        <div className="h-20 bg-gray-800 rounded"></div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-2 overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
});
MermaidBlock.displayName = "MermaidBlock";

interface CodeBlockProps {
  className?: string;
  children?: React.ReactNode;
}

const CodeBlock = ({ className, children }: CodeBlockProps) => {
  const match = /language-(\w+)/.exec(className || "");
  const language = match ? match[1] : "";
  const code = String(children).replace(/\n$/, "");

  // Handle mermaid code blocks
  if (language === "mermaid") {
    return <MermaidBlock code={code} />;
  }

  // Regular code block
  return (
    <pre className="bg-gray-800 border border-gray-700 rounded p-3 overflow-x-auto">
      <code className={className}>{children}</code>
    </pre>
  );
};

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export const MarkdownRenderer = memo<MarkdownRendererProps>(({ content, className }) => {
  return (
    <div className={`prose prose-sm max-w-none prose-invert ${className || ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Custom code block handler for mermaid
          code: ({ className, children, ...props }) => {
            const isInline = !className;
            if (isInline) {
              return (
                <code className="bg-gray-700 px-1 py-0.5 rounded text-sm" {...props}>
                  {children}
                </code>
              );
            }
            return <CodeBlock className={className}>{children}</CodeBlock>;
          },
          // Style pre blocks
          pre: ({ children }) => <>{children}</>,
          // Style links
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 underline"
            >
              {children}
            </a>
          ),
          // Style tables
          table: ({ children }) => (
            <table className="border-collapse border border-gray-700 my-2">
              {children}
            </table>
          ),
          th: ({ children }) => (
            <th className="border border-gray-700 bg-gray-800 px-3 py-1 text-left">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-gray-700 px-3 py-1">{children}</td>
          ),
          // Style blockquotes
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-blue-500 pl-4 my-2 text-gray-300 italic">
              {children}
            </blockquote>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
MarkdownRenderer.displayName = "MarkdownRenderer";

export default MarkdownRenderer;
