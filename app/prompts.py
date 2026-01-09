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
"""

# 3. SAFETY & DATES
SAFETY_PROTOCOL = """
### OPERATIONAL RULES:
1. **NO HALLUCINATIONS:** If the Search/Memory yields nothing, admit it.
2. **TEMPORAL AWARENESS:** Today is {current_date}.
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


def build_system_prompt(memories: list[str] = None, search_context: str = None) -> str:
    """
    Constructs the final system prompt dynamically.
    Args:
        memories: List of strings from VectorDB
        search_context: Pre-formatted string from format_search_results()
    """
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    
    # 1. Memory Block
    if memories:
        memory_block = "\n### 🧠 LONG-TERM MEMORY:\n" + "\n".join([f"- {m}" for m in memories]) + "\n"
    else:
        memory_block = ""

    # 2. Search Block (Dynamic Injection)
    # If we just performed a search, this variable will contain the data
    web_block = ""
    if search_context:
        web_block = f"\n{search_context}\n"

    # Assemble
    full_prompt = f"""
{BASE_IDENTITY}

{TOOL_INSTRUCTIONS}

{SAFETY_PROTOCOL.format(current_date=current_date)}

{memory_block}

{web_block}

### FINAL INSTRUCTION:
If you have Search Results or Memories above, use them to answer. 
If the user asks a new question requiring data you don't have, issue a [SEARCH: ...] command.
"""
    return full_prompt.strip()
