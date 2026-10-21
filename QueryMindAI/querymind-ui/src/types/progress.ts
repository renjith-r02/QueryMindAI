/**
 * One step of a running question, as streamed by querymind-api (`progress` events).
 * The same id is sent "running" and then "done" or "failed", so steps update in place.
 */
export type ProgressStep = {
  id: string;
  status: "running" | "done" | "failed";
  message: string;
  detail?: Record<string, unknown>;
};
