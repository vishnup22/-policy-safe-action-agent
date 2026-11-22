import type { Metadata } from "next";
import { EvalRunDetail } from "./eval-run-detail";

export const metadata: Metadata = { title: "Eval run" };

export default async function EvalRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <EvalRunDetail runId={decodeURIComponent(runId)} />;
}
