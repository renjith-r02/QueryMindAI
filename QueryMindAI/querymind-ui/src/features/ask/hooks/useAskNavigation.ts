import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAskStore } from "@/features/ask/store";

/** Ask a question or reopen a saved run, then show it on the Ask page. */
export function useAskNavigation() {
  const ask = useAskStore((state) => state.ask);
  const openRun = useAskStore((state) => state.openRun);
  const navigate = useNavigate();

  return {
    ask: useCallback(
      (question: string) => {
        if (!question.trim()) return;
        void ask(question);
        void navigate("/ask");
      },
      [ask, navigate],
    ),
    open: useCallback(
      (runId: string) => {
        openRun(runId);
        void navigate("/ask");
      },
      [openRun, navigate],
    ),
  };
}
