"use client";

import {
  BracesIcon,
  CheckCircle2Icon,
  DatabaseIcon,
  FileQuestionIcon,
  RouteIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";

import { jsonText } from "./format";

interface ToolEventDetailsProps {
  content: Record<string, unknown>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function JsonPanel({ value }: { value: unknown }) {
  return (
    <pre className="bg-muted/35 max-h-[320px] overflow-auto rounded-md border p-3 text-xs whitespace-pre-wrap">
      {jsonText(value)}
    </pre>
  );
}

function DetailSection({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="min-w-0 rounded-lg border bg-background">
      <div className="text-muted-foreground flex items-center gap-2 border-b px-4 py-3 text-xs font-semibold">
        {icon}
        {title}
      </div>
      <div className="space-y-3 p-4">{children}</div>
    </section>
  );
}

function CypherBlock({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  if (typeof value !== "string" || !value.trim()) return null;
  return (
    <div className="min-w-0">
      <div className="text-muted-foreground mb-1.5 text-xs font-medium">
        {label}
      </div>
      <pre className="overflow-auto rounded-md border border-blue-500/20 bg-slate-950 p-3 font-mono text-xs whitespace-pre-wrap text-slate-100">
        {value}
      </pre>
    </div>
  );
}

function Text2CypherTrace({ trace }: { trace: Record<string, unknown> }) {
  const generation = isRecord(trace.generation) ? trace.generation : {};
  const validation = isRecord(trace.validation) ? trace.validation : {};
  const execution = isRecord(trace.execution) ? trace.execution : {};
  const querySteps = Array.isArray(trace.queries)
    ? trace.queries.filter(isRecord)
    : [];

  return (
    <DetailSection
      title="Text2Cypher Trace"
      icon={<DatabaseIcon className="size-3.5" />}
    >
      <div className="flex flex-wrap gap-2">
        {typeof validation.valid === "boolean" && (
          <Badge variant={validation.valid ? "default" : "destructive"}>
            <CheckCircle2Icon className="size-3" />
            Validation {validation.valid ? "passed" : "failed"}
          </Badge>
        )}
        {typeof execution.row_count === "number" && (
          <Badge variant="secondary">{execution.row_count} result rows</Badge>
        )}
      </div>
      <CypherBlock
        label="Generated Cypher"
        value={generation.generated_cypher}
      />
      <CypherBlock
        label="Normalized Cypher"
        value={validation.normalized_cypher}
      />
      <CypherBlock
        label="Executed Cypher"
        value={execution.normalized_cypher}
      />
      {querySteps.map((step, index) => {
        const stage =
          typeof step.stage === "string" && step.stage.trim()
            ? step.stage
            : `step-${index + 1}`;
        const stepValidation = isRecord(step.validation)
          ? step.validation
          : {};
        const stepExecution = isRecord(step.execution) ? step.execution : {};
        const stageLabel = stage
          .split(/[_-]/)
          .filter(Boolean)
          .map((part) => part[0]?.toUpperCase() + part.slice(1))
          .join(" ");

        return (
          <div className="space-y-3 rounded-md border p-3" key={`${stage}:${index}`}>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{stageLabel}</Badge>
              {typeof stepExecution.row_count === "number" && (
                <span className="text-muted-foreground text-xs">
                  {stepExecution.row_count} rows
                </span>
              )}
            </div>
            <CypherBlock
              label={`${stageLabel} Query Cypher`}
              value={step.generated_cypher}
            />
            <CypherBlock
              label={`${stageLabel} Normalized Cypher`}
              value={stepValidation.normalized_cypher}
            />
            {step.parameters !== undefined && (
              <div>
                <div className="text-muted-foreground mb-1.5 text-xs font-medium">
                  Parameters
                </div>
                <JsonPanel value={step.parameters} />
              </div>
            )}
          </div>
        );
      })}
      <JsonPanel value={trace} />
    </DetailSection>
  );
}

export function ToolEventDetails({ content }: ToolEventDetailsProps) {
  const request = isRecord(content.request) ? content.request : null;
  const trace = isRecord(content.trace) ? content.trace : null;
  const result = content.result;
  const isText2CypherTrace =
    trace !== null &&
    (isRecord(trace.generation) ||
      isRecord(trace.validation) ||
      isRecord(trace.execution) ||
      Array.isArray(trace.queries));

  return (
    <div className="grid gap-3 border-b bg-muted/10 p-4 xl:grid-cols-2">
      {request && (
        <DetailSection
          title="Request"
          icon={<FileQuestionIcon className="size-3.5" />}
        >
          <JsonPanel value={request} />
        </DetailSection>
      )}

      {isText2CypherTrace && trace ? (
        <Text2CypherTrace trace={trace} />
      ) : (
        trace && (
          <DetailSection
            title="MCP Trace"
            icon={<RouteIcon className="size-3.5" />}
          >
            <JsonPanel value={trace} />
          </DetailSection>
        )
      )}

      {result !== undefined && (
        <DetailSection title="Result" icon={<BracesIcon className="size-3.5" />}>
          <JsonPanel value={result} />
        </DetailSection>
      )}
    </div>
  );
}
