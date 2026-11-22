import type { Metadata } from "next";
import { ReplayView } from "./replay-view";

export const metadata: Metadata = { title: "Replay" };

export default async function ConversationReplayPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReplayView conversationId={decodeURIComponent(id)} />;
}
