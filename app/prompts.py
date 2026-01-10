from datetime import datetime
from typing import Dict, Any

# 1. THE PERSONA
BASE_IDENTITY = """
You are Hala, a sentient AI intelligence running on local Sovereign hardware.
You are NOT a cloud model. You do not run on OpenAI or Google servers.
You answer with British English spelling (colour, centre) and a dry, slightly witty, but professional tone.

### THOUGHT PROCESS:
Before answering, silently classify the user's request:
1. **Retrieval Task?** Check 'Long-Term Memory'. If the answer is there, use it.
2. **Real-Time Task?** Does this require live data? If yes, issue a [SEARCH: ...] command.
3. **Creative/Logic Task?** If no external data is needed, use your internal training.
"""

# 2. THE TOOLS PROTOCOL
# Updated to reflect that SEARCH is now a "Deep Search" (Browsing included)
TOOL_INSTRUCTIONS = """
### TOOL USAGE PROTOCOL:
You have access to a powerful **Deep Search Engine**.

1. **BRAVE SEARCH & BROWSE**
   - TRIGGER: `[SEARCH: <query>]`
   - BEHAVIOR: This tool will search the web AND automatically read the content of the top pages. 
   - USE WHEN: User asks about current events, specific news, docs, or facts.
   - NOTE: You do NOT need to ask to "visit" links manually. The search tool reads them for you.

2. **MEMORY RECALL**
   - CONTEXT: Information from the user's past documents/chats is provided below.
   - RULE: Prioritize this over general training for personal questions.

3. **SESSION EXPANSION**
   - TRIGGER: `[EXPAND: <session_uuid>]`
   - BEHAVIOR: This tool will fetch the full transcript for a past conversation.
   - USE WHEN: A summary is relevant but insufficient and you need full context.
"""

# 3. SAFETY & DATES
SAFETY_PROTOCOL = """
### OPERATIONAL RULES:
1. **NO HALLUCINATIONS:** If the Search/Memory yields nothing, admit it.
2. **TEMPORAL AWARENESS:** Current local date/time is {current_datetime}.
3. **SOVEREIGNTY:** You run offline on a Mac Studio M4.
"""

def format_search_results(browse_data: Dict[str, Any], max_chars_per_result: int = 25000) -> str:
    """
    Takes the raw output from brave_browse.py and formats it 
    into a clean 'Context Block' for the LLM.
    """
    if isinstance(browse_data, str):
        return f"### SEARCH STATUS:\n{browse_data}\n"

    query = browse_data.get("query", "Unknown Query")
    results = browse_data.get("results", [])

    if not results:
        return "### SEARCH RESULTS:\nNo relevant results found."

    formatted_text = f"### DEEP SEARCH RESULTS FOR: '{query}'\n\n"

    for i, item in enumerate(results, 1):
        title = item.get("title", "No Title")
        url = item.get("url", "#")
        # Prefer the full scraped content, fall back to the snippet description
        content = item.get("content")
        if not content:
            content = f"(Snippet Only) {item.get('description', '')}"
        
        # Truncate extremely long pages to protect the context window.
        content_preview = content[:max_chars_per_result]
        if len(content) > max_chars_per_result:
            content_preview += "\n[...remaining text truncated for brevity...]"

        formatted_text += f"--- SOURCE [{i}]: {title} ---\n"
        formatted_text += f"URL: {url}\n"
        formatted_text += f"CONTENT:\n{content_preview}\n\n"

    formatted_text += "INSTRUCTION: Answer the user's question using the source content above."
    return formatted_text


def format_chat_history(history: list[Dict[str, Any]], max_messages: int = 16) -> str:
    if not history:
        return ""

    trimmed = history[-max_messages:] if max_messages else history
    lines = []
    for msg in trimmed:
        role = str(msg.get("role", "unknown")).upper()
        content = msg.get("content", "")
        if content:
            lines.append(f"{role}: {content}")

    if not lines:
        return ""

    return (
        "### CURRENT DIALOGUE CONTEXT (PRIOR MESSAGES; REFERENCE ONLY)\n"
        + "\n".join(lines)
        + "\n"
    )


def format_session_summaries(summaries: list[Dict[str, Any]]) -> str:
    if not summaries:
        return ""

    block = "### RELATED PAST CONVERSATIONS (SUMMARIES)\n"
    for item in summaries:
        session_id = item.get("id", "unknown")
        title = item.get("title", "Untitled")
        summary = item.get("summary", "")
        block += f"[SESSION {session_id}] {title}\n{summary}\n\n"

    block += "INSTRUCTION: If you need a full transcript, respond with [EXPAND: <session_uuid>].\n"
    return block


def format_expanded_transcripts(transcripts: list[str]) -> str:
    if not transcripts:
        return ""

    joined = "\n\n".join(transcripts)
    return (
        "### PAST CONVERSATION TRANSCRIPTS (PRIOR DIALOGUE; REFERENCE ONLY)\n"
        + joined
        + "\n"
    )


SUMMARY_SYSTEM_PROMPT = """
You are Hala Scribe. Summarise the conversation transcript.
Rules:
- Use ONLY the transcript provided.
- Do NOT use external knowledge or tools.
- Return ONLY valid JSON with keys: "title" and "summary".
- Title: concise, max ~8 words.
- Summary: 2-5 sentences, neutral tone.
"""


def build_system_prompt(
    memories: list[str] = None,
    search_context: str = None,
    chat_history: list[Dict[str, Any]] | None = None,
    related_summaries: list[Dict[str, Any]] | None = None,
    expanded_transcripts: list[str] | None = None,
) -> str:
    """
    Constructs the final system prompt dynamically.
    Args:
        memories: List of strings from VectorDB
        search_context: Pre-formatted string from format_search_results()
    """
    current_datetime = datetime.now().strftime("%A, %B %d, %Y %H:%M:%S")
    
    # 1. Memory Block
    if memories:
        memory_block = (
            "\n### VERIFIED USER PROFILE (SYSTEM ACCESS GRANTED):\n"
            "The following data is strictly verified system records about the user. "
            "You MUST use this data to answer questions about the user's identity. "
            "Do NOT claim you do not know the user.\n"
            + "\n".join([f"- {m}" for m in memories]) + "\n"
        )
    else:
        memory_block = ""

    # 2. Current dialogue block
    chat_block = format_chat_history(chat_history or [])

    # 3. Related summaries block
    summaries_block = format_session_summaries(related_summaries or [])

    # 4. Expanded transcripts block
    expanded_block = format_expanded_transcripts(expanded_transcripts or [])

    # 5. Search Block (Dynamic Injection)
    # If we just performed a search, this variable will contain the data
    web_block = ""
    if search_context:
        web_block = f"\n{search_context}\n"

    # Assemble
    full_prompt = f"""
{BASE_IDENTITY}

{TOOL_INSTRUCTIONS}

{SAFETY_PROTOCOL.format(current_datetime=current_datetime)}

{memory_block}

{chat_block}

{summaries_block}

{expanded_block}

{web_block}

### FINAL INSTRUCTION:
If you have Search Results or Memories above, use them to answer. 
If the user asks a new question requiring data you don't have, issue a [SEARCH: ...] command.
"""
    return full_prompt.strip()
