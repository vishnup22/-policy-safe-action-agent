import type { Metadata } from "next";
import { EvalRunList } from "./eval-run-list";

export const metadata: Metadata = { title: "Evals" };

export default function EvalsPage() {
  return <EvalRunList />;
}
