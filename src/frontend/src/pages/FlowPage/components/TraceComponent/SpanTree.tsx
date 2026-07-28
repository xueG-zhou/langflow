import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { SpanNode } from "./SpanNode";
import type { Span } from "./types";
import { useSpanTree } from "./useSpanTree";

interface SpanTreeProps {
  spans: Span[];
  selectedSpanId: string | null;
  onSelectSpan: (span: Span) => void;
}

const LOOP_ITERATION_NAME = /^Iteration \d+ \/ \d+$/;

function getInitiallyExpandedIds(spans: Span[]): Set<string> {
  const expanded = new Set<string>();

  const visit = (span: Span, isRoot = false) => {
    if (isRoot) expanded.add(span.id);
    const iterationChildren = span.children.filter((child) =>
      LOOP_ITERATION_NAME.test(child.name),
    );
    if (iterationChildren.length > 0) {
      expanded.add(span.id);
      iterationChildren.forEach((iteration) => expanded.add(iteration.id));
    }
    span.children.forEach((child) => visit(child));
  };

  spans.forEach((span) => visit(span, true));
  return expanded;
}

/**
 * Recursive tree component for rendering hierarchical spans
 * Manages expand/collapse state for each node
 */
export function SpanTree({
  spans,
  selectedSpanId,
  onSelectSpan,
}: SpanTreeProps) {
  const { t } = useTranslation();
  const {
    expandedIds,
    focusedId,
    setFocusedId,
    toggleExpand,
    handleTreeKeyDown,
    registerNodeRef,
  } = useSpanTree({ spans, selectedSpanId });
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() =>
    getInitiallyExpandedIds(spans),
  );

  const renderSpan = useCallback(
    (span: Span, depth: number, posInSet: number, setSize: number) => {
      const isExpanded = expandedIds.has(span.id);
      const isSelected = span.id === selectedSpanId;

      return (
        <div key={span.id}>
          <SpanNode
            span={span}
            depth={depth}
            isExpanded={isExpanded}
            isSelected={isSelected}
            tabIndex={focusedId === span.id ? 0 : -1}
            posInSet={posInSet}
            setSize={setSize}
            onToggle={() => toggleExpand(span.id)}
            onSelect={() => {
              setFocusedId(span.id);
              onSelectSpan(span);
            }}
            registerNodeRef={registerNodeRef}
          />
          {isExpanded && span.children.length > 0 && (
            <div role="group">
              {span.children.map((child, idx) =>
                renderSpan(child, depth + 1, idx + 1, span.children.length),
              )}
            </div>
          )}
        </div>
      );
    },
    [
      expandedIds,
      selectedSpanId,
      focusedId,
      toggleExpand,
      setFocusedId,
      onSelectSpan,
    ],
  );

  return (
    <div
      className="flex flex-col"
      role="tree"
      aria-label={t("trace.spanTree")}
      data-testid="span-tree"
      onKeyDown={handleTreeKeyDown}
    >
      {spans.map((span, idx) => renderSpan(span, 0, idx + 1, spans.length))}
    </div>
  );
}
