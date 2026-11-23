import type { Metadata } from "next";
import { ConversationList } from "./conversation-list";

export const metadata: Metadata = { title: "Conversations" };

export default function ConversationsPage() {
  return <ConversationList />;
}
