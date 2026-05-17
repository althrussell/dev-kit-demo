import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Renders model-generated markdown (Agent Bricks responses, Genie summaries,
// etc.) with GFM tables and footnotes, themed for the dark dashboard. Wide
// tables and code blocks scroll horizontally inside this container so they
// can never push the surrounding grid/flex layout.
export function MarkdownBody({
  source,
  className = '',
  size = 'sm',
}: {
  source: string;
  className?: string;
  size?: 'xs' | 'sm' | 'base';
}) {
  const baseText =
    size === 'xs'
      ? 'text-[12px]'
      : size === 'base'
        ? 'text-sm'
        : 'text-[13px]';
  return (
    <div
      className={`${baseText} leading-relaxed text-text-secondary min-w-0 break-words ${className}`}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-base font-semibold text-text-primary mt-4 mb-2 first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-sm font-semibold text-text-primary mt-4 mb-2 first:mt-0 uppercase tracking-wider">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-[13px] font-semibold text-text-primary mt-3 mb-1.5 first:mt-0">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="my-2 first:mt-0 last:mb-0">{children}</p>
          ),
          strong: ({ children }) => (
            <strong className="text-text-primary font-semibold">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          ul: ({ children }) => (
            <ul className="list-disc pl-5 my-2 space-y-1 marker:text-electric-cyan/70">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 my-2 space-y-1 marker:text-electric-cyan/70">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="pl-1">{children}</li>,
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="text-electric-cyan hover:underline break-all"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-electric-cyan/40 pl-3 my-2 text-text-secondary/90 italic">
              {children}
            </blockquote>
          ),
          code: ({ inline, children, ...props }: any) =>
            inline ? (
              <code
                className="px-1 py-0.5 rounded bg-deep-navy/70 border border-border/40 text-[12px] font-mono text-text-primary"
                {...props}
              >
                {children}
              </code>
            ) : (
              <code className="block font-mono text-[12px] text-text-primary" {...props}>
                {children}
              </code>
            ),
          pre: ({ children }) => (
            <pre className="my-3 rounded-md bg-deep-navy/70 border border-border/40 p-3 overflow-x-auto text-[12px] leading-relaxed">
              {children}
            </pre>
          ),
          hr: () => <hr className="my-4 border-border/40" />,
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-md border border-border/40">
              <table className="w-full text-[12px] border-collapse">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-panel-soft/60 text-text-primary">{children}</thead>
          ),
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => (
            <tr className="border-b border-border/30 last:border-0">{children}</tr>
          ),
          th: ({ children }) => (
            <th className="text-left font-medium px-3 py-2 whitespace-nowrap">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 align-top text-text-secondary">{children}</td>
          ),
          sup: ({ children }) => (
            <sup className="text-[10px] text-electric-cyan/80 font-mono">{children}</sup>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
