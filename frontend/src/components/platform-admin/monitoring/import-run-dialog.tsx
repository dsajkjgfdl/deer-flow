"use client";

import { UploadIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  parseImportedRunTimeline,
  type MonitoringRunTimeline,
} from "@/core/platform";

interface ImportRunDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: (timeline: MonitoringRunTimeline) => void;
}

export function ImportRunDialog({
  open,
  onOpenChange,
  onImported,
}: ImportRunDialogProps) {
  const [jsonTextValue, setJsonTextValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      setJsonTextValue(text);
      setError(null);
    } catch {
      setError("Unable to read JSON file.");
    }
  }

  function handleImport() {
    const result = parseImportedRunTimeline(jsonTextValue);
    if (!result.ok) {
      setError(result.error);
      return;
    }

    onImported(result.data);
    setError(null);
    setJsonTextValue("");
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import run timeline</DialogTitle>
          <DialogDescription>Single run timeline JSON.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <label className="text-sm font-medium" htmlFor="run-json-file">
              JSON file
            </label>
            <Input
              id="run-json-file"
              accept=".json,application/json"
              type="file"
              onChange={handleFileChange}
            />
          </div>

          <div className="grid gap-1.5">
            <label className="text-sm font-medium" htmlFor="run-json-text">
              JSON content
            </label>
            <Textarea
              id="run-json-text"
              className="min-h-[260px] font-mono text-xs"
              value={jsonTextValue}
              onChange={(event) => {
                setJsonTextValue(event.target.value);
                setError(null);
              }}
            />
          </div>

          {error && <div className="text-destructive text-sm">{error}</div>}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            disabled={jsonTextValue.trim().length === 0}
            onClick={handleImport}
          >
            <UploadIcon className="size-4" />
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
