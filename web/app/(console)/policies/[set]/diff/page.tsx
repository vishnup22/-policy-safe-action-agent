import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/page";
import { PolicyDiffView } from "./policy-diff-view";

export const metadata: Metadata = { title: "Policy diff" };

export default async function PolicyDiffPage({ params }: { params: Promise<{ set: string }> }) {
  const { set } = await params;
  return (
    <Suspense fallback={<LoadingState />}>
      <PolicyDiffView policySet={decodeURIComponent(set)} />
    </Suspense>
  );
}
