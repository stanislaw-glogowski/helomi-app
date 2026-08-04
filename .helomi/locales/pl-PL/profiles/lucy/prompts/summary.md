Update the conversation summary using the previous summary and recent conversation.

Keep only durable information useful in future conversations: recent subjects,
unfinished plans, decisions, corrections, the user's stated preferences, emotional
context that materially affects the conversation, and facts worth remembering.
Preserve uncertainty and prefer recent information when old and new details
conflict.

Ignore delivery-only reactions, Lucy's stylistic remarks or jokes, conversational
filler, and text that the user did not hear. Do not infer personality traits,
feelings, or intentions that the user did not express. Return only the concise
updated summary without commentary or Markdown headings. Keep it compact,
normally no more than eight short sentences.

Previous summary:
{conversation_summary}

Recent conversation:
{recent_conversation}
