"""
Cognitive Engine – Central nervous system of ELI.
FIXED: missing methods added, true token streaming implemented.
"""

import threading
import time
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, Generator, List
from .memory import get_memory
from .scheduler import get_scheduler
from ..tools.router_enhanced import route
from ..tools.executor_enhanced import execute, memory_recall
from .llm_intent import parse_cached
from .self_improvement import get_self_improvement


def execute(action, args=None):
    from eli.tools import executor_enhanced as _ex
    return _ex.execute(action, args or {})
from . import config  # for temperature
try:
    from . import gguf_inference  # module-level attr for mocking
except Exception:
    gguf_inference = None


# ============================================================
# LOAD PERSONA FROM persona.txt (cleaned of Ollama directives)
# ============================================================
_PERSONA_FILE = Path(__file__).parent / "persona.txt"

def _clean_persona(raw: str) -> str:
    """Strip Ollama Modelfile directives (PARAMETER, TEMPLATE, FROM) that
    pollute the GGUF system prompt and waste context tokens."""
    clean_lines = []
    in_template_block = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith(("PARAMETER ", "FROM ")):
            continue
        if stripped.upper().startswith("TEMPLATE "):
            in_template_block = True
            continue
        if in_template_block:
            if '"""' in stripped:
                in_template_block = False
            continue
        if stripped.startswith("# Model parameters") or stripped.startswith("# Template for conversation"):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).rstrip()

if _PERSONA_FILE.exists():
    PERSONA = _clean_persona(_PERSONA_FILE.read_text(encoding="utf-8", errors="replace"))
else:
    PERSONA = "You are ELI, a helpful AI assistant."
# ============================================================

class CognitiveEngine:
    def __init__(self):
        self.memory = get_memory()
        self.scheduler = get_scheduler()
        self.session_id = str(int(time.time()))
        self.running = True
        self._gguf_available = False
        self._init_gguf()
        self._start_reflection_loop()
        self._start_habit_loop()
        self._start_proactive_listener()
        
        # Load persistent user ID
        self.user_id = self._get_user_id()
    
    def _get_user_id(self) -> str:
        """Load or create persistent user ID."""
        user_id_file = Path.home() / '.eli_user_id'
        if user_id_file.exists():
            return user_id_file.read_text().strip()
        else:
            import uuid
            user_id = str(uuid.uuid4())
            user_id_file.write_text(user_id)
            return user_id
    
    def _init_gguf(self):
        """Initialize GGUF connection."""
        try:
            from . import gguf_inference
            if gguf_inference.get_model_path():
                self._gguf_available = True
                print("[COGNITIVE] GGUF connection established")
            else:
                print("[COGNITIVE] No GGUF model found")
        except Exception as e:
            print(f"[COGNITIVE] GGUF init failed: {e}")
            self._gguf_available = False

    def _extract_last_n(self, query: str) -> Optional[int]:
        """Extract number from 'last N conversations'."""
        m = re.search(r'last\s+(\d+)\s+(?:conversations|messages|turns)', query.lower())
        return int(m.group(1)) if m else None

    def _extract_since_date(self, query: str) -> Optional[str]:
        """Extract date from 'since Jan 29' or 'from January 29th'."""
        months = r'(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
        m = re.search(r'(?:since|from|after)\s+' + months + r'\s+(\d{1,2})(?:st|nd|rd|th)?', query.lower())
        if m:
            month = m.group(1)[:3].capitalize()
            day = m.group(2)
            current_year = time.localtime().tm_year
            date_str = f"{month} {day} {current_year}"
            try:
                struct = time.strptime(date_str, "%b %d %Y")
                return time.strftime("%Y-%m-%d", struct)
            except:
                pass
        return None

    def _retrieve_relevant_memories(self, query: str, limit: int = 20) -> str:
        """Fetch memories with NO LIMIT when appropriate."""
        context_parts = []
        
        fetch_limit = 150  # default recall limit
        if "summarise" in query.lower() or "summarize" in query.lower() or "recap" in query.lower():
            fetch_limit = 500
        n = self._extract_last_n(query)
        if n is not None:
            fetch_limit = n
        since_date = self._extract_since_date(query)
        
        print(f"[MEMORY] Fetch strategy: limit={fetch_limit}, since={since_date}")
        
        # ----- 1. Fetch conversations (date‑based if requested) -----
        # NOTE: No user_id filter. Single-user local system — old conversations
        # were stored with different user_ids and would be hidden.
        try:
            if since_date:
                all_recent = self.memory.get_recent_conversation(limit=1000)
                filtered = []
                for turn in all_recent:
                    ts = turn.get("timestamp", 0)
                    date = time.strftime("%Y-%m-%d", time.localtime(ts))
                    if date >= since_date:
                        filtered.append(turn)
                conversations = filtered[-fetch_limit:] if fetch_limit < len(filtered) else filtered
            else:
                conversations = self.memory.get_recent_conversation(limit=fetch_limit)
            
            print(f"[MEMORY] Fetched {len(conversations)} conversations.")
            if conversations:
                # get_recent_conversation returns newest-first (ORDER BY timestamp DESC).
                # Reverse to chronological (oldest first) so the LLM reads the thread
                # in the correct order and can reconstruct multi-turn state.
                chronological = list(reversed(conversations))
                lines = []
                for i, turn in enumerate(chronological, 1):
                    role = "User" if turn.get("role") == "user" else "ELI"
                    ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(turn.get("timestamp", 0)))
                    content = turn.get("content", "").replace("\n", " ")[:200]
                    lines.append(f"[{i:03d}] [{ts}] {role}: {content}")
                context_parts.append("Conversation history (chronological, oldest→newest):\n" + "\n".join(lines))
        except Exception as e:
            print(f"[MEMORY] Conversation retrieval failed: {e}")
        
        # ----- 2. Semantic search (always) -----
        try:
            if query:
                results = self.memory.search_conversations(query, limit=limit*2)
                if results:
                    lines = []
                    for turn in results[:5]:
                        role = "User" if turn.get("role") == "user" else "ELI"
                        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(turn.get("timestamp", 0)))
                        content = turn.get("content", "").replace("\n", " ")[:150]
                        lines.append(f"[{ts}] {role}: {content}")
                    context_parts.append("Semantically relevant conversations:\n" + "\n".join(lines))
        except Exception as e:
            print(f"[MEMORY] Semantic search failed: {e}")
        
        # ----- 3. Explicit memories (from Memory.recall_memory) -----
        try:
            if query:
                print(f"[MEMORY] Searching stored memories for: {query[:50]}...")
                mem_results = self.memory.recall_memory(query=query, limit=limit)
                pdf_results = self.memory.recall_memory(query="pdf_analysis " + query, limit=5)
                mem_results = mem_results + [r for r in pdf_results if r not in mem_results]
                print(f"[MEMORY] Stored memory search returned: {len(mem_results) if mem_results else 0} results")
                if mem_results:
                    lines = []
                    for mem in mem_results[:5]:
                        text = mem.get("text", "").replace("\n", " ")[:200]
                        tags = mem.get("tags", [])
                        if isinstance(tags, list):
                            tags = ", ".join(tags)
                        lines.append(f"- {text} [{tags}]")
                    if lines:
                        context_parts.append("Stored knowledge:\n" + "\n".join(lines))
        except Exception as e:
            print(f"[MEMORY] Memory recall failed: {e}")
            import traceback
            traceback.print_exc()
        
        # ----- 4. Self-reflections (deduplicated) -----
        try:
            reflections = self.memory.recall_memory("reflection", limit=10)
            if reflections:
                unique = {}
                for ref in reflections:
                    text = ref.get("text", "").replace("\n", " ")[:100]
                    unique[text] = ref
                lines = [f"- {text}" for text in unique.keys()]
                if lines:
                    context_parts.append("Recent self-reflections:\n" + "\n".join(lines[:3]))
        except Exception as e:
            print(f"[MEMORY] Reflection recall failed: {e}")
        
        full_context = "\n\n".join(context_parts)
        print(f"[MEMORY] Final context length: {len(full_context)} chars")
        return full_context

    def process(self, user_input: str, source: str = "user", stream: bool = False) -> Any:
        """Process user input with memory context and self-improvement."""
        # Only re-fetch if not already injected (allows test mocking)
        if not hasattr(self, 'memory') or self.memory is None:
            self.memory = get_memory()
        self.memory.add_conversation_turn("user", user_input, self.session_id, self.user_id)
        
        # Get recent context — do NOT filter by user_id/session_id (single-user system)
        context = self.memory.get_recent_conversation(5)
        intent = self._parse_intent(user_input, context)
        
        if intent.get("confidence", 0) < 0.5:
            try:
                si = get_self_improvement()
                si.memory.log_failure(user_input, error="Low confidence", confidence=intent.get("confidence", 0), context={"intent": intent})
            except Exception as e:
                print(f"[SELF] Failed to log: {e}")
        
        action = intent.get("action", "CHAT")
        args = intent.get("args", {})

        if action == "CHAT" or action == "chat":
            if stream:
                return self._stream_chat(user_input, args, context)
            else:
                try:
                    memory_context = self._retrieve_relevant_memories(user_input)
                    response = self._get_chat_response(user_input, memory_context)
                    result = {
                        'ok': True,
                        'action': 'CHAT',
                        'content': response,
                        'response': response
                    }
                    self.memory.add_conversation_turn("assistant", response, self.session_id, self.user_id)
                    return result
                except Exception as e:
                    print(f"[COGNITIVE] Chat failed: {e}")
                    return {'ok': False, 'action': 'CHAT', 'error': str(e), 'content': f"I encountered an error: {e}"}
        
        result = execute(action, args)
        if not result.get("ok", False):
            try:
                si = get_self_improvement()
                si.memory.log_failure(user_input, error=result.get("error", "Unknown error"), confidence=intent.get("confidence", 0), context={"intent": intent, "result": result})
            except Exception as e:
                print(f"[SELF] Failed to log: {e}")
        
        response = result.get("content", "")
        self.memory.add_conversation_turn("assistant", response, self.session_id, self.user_id)
        self._learn_from_result(intent, result)
        return result

    def _parse_intent(self, text: str, context: list) -> Dict[str, Any]:
        try:
            from .router import route
            from eli.tools.router_enhanced import route as _route
            router_intent = _route(text)
            if router_intent and router_intent.get('confidence', 0) > 0.5:
                print(f"[COGNITIVE] Router parsed: {router_intent}")
                return router_intent
        except Exception as e:
            print(f"[COGNITIVE] Router failed: {e}")
        return {"action": "CHAT", "args": {"message": text}, "confidence": 0.5}


    def _truncate_context(self, prompt: str, max_chars: int = 10000) -> str:
        """Hard-cap prompt length to avoid exceeding n_ctx=4096 token window.
        Keeps the system header + tail (most recent conversation).
        """
        if len(prompt) <= max_chars:
            return prompt
        # Find where conversation history starts
        hist_marker = "Conversation history"
        idx = prompt.find(hist_marker)
        if idx < 0:
            return prompt[:max_chars]
        header = prompt[:idx]
        history = prompt[idx:]
        # Keep header, trim history from the TOP (oldest turns)
        budget = max_chars - len(header)
        if budget < 500:
            budget = 500
        trimmed = history[-budget:]
        # Try to start at a clean turn boundary
        newline = trimmed.find("\n")
        if newline > 0:
            trimmed = trimmed[newline:]
        return header + "...[older history trimmed]\n" + trimmed

    def _get_chat_response(self, prompt: str, memory_context: str = "") -> str:
        """Non‑streaming chat response (full string)."""
        if not self._gguf_available:
            self._init_gguf()
            if not self._gguf_available:
                return ("No model found. Put a .gguf file in ELI's models folder (~/.local/share/eli/models) "
                    "or set ELI_GGUF_MODEL_PATH, then restart ELI.")
        
        try:
            from . import gguf_inference
            
            enhanced_system = (
                f"{PERSONA}\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "CONVERSATION CONTINUITY — READ THIS CAREFULLY\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "The CONVERSATION HISTORY below is YOUR ongoing dialogue with the user.\n"
                "It is listed in chronological order (oldest first, newest last).\n"
                "The most recent User message is the one you are now responding to.\n\n"
                "CRITICAL RULES:\n"
                "1. You MUST read the full history before responding.\n"
                "2. You are CONTINUING this conversation — not starting a new one.\n"
                "3. If a task or game is in progress (e.g. 20 questions, a list, a count),\n"
                "   reconstruct its current state ONLY from facts explicitly stated in the history.\n"
                "4. NEVER restart or re-introduce a task already in progress.\n"
                "5. NEVER ask questions already asked or answered in the history.\n"
                "6. Keep an accurate running count of anything being counted in the conversation.\n"
                "7. FACTS ONLY IN RECAPS: When summarising what you know, include ONLY facts\n"
                "   the user explicitly confirmed. NEVER infer, assume, or invent facts.\n"
                "   If you are unsure whether something was confirmed, leave it out.\n"
                "8. You are an AI assistant running locally. You CANNOT run background processes,\n"
                "   schedule future tasks, or generate reports autonomously. Be honest about this.\n\n"
            )
            if memory_context:
                enhanced_system += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                enhanced_system += f"CONVERSATION HISTORY & STORED KNOWLEDGE:\n"
                enhanced_system += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                enhanced_system += f"{memory_context}\n\n"
            else:
                enhanced_system += "No prior conversation history.\n\n"
            enhanced_system += (
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Now respond to the latest User message, continuing naturally from where the conversation left off:\n"
            )
            
            print(f"[COGNITIVE] Generating response...")
            
            response = gguf_inference.chat_completion(
                prompt,
                system=enhanced_system,
                max_tokens=2048,
                temperature=config.get_temperature()  # use config
            )
            return response.strip() if response else "I received an empty response."
        except Exception as e:
            print(f"[COGNITIVE] GGUF chat failed: {e}")
            return f"I encountered an error while generating a response: {e}"

    def _stream_chat_response(self, user_input: str, memory_context: str = "") -> Generator[str, None, None]:
        """
        Generate a streaming response using GGUF, yielding tokens one by one.
        """
        if not self._gguf_available:
            self._init_gguf()
            if not self._gguf_available:
                yield ("No model found. Put a .gguf file in ELI's models folder (~/.local/share/eli/models) "
                    "or set ELI_GGUF_MODEL_PATH, then restart ELI.")
                return

        from . import gguf_inference

        # Build the enhanced system prompt (identical to _get_chat_response)
        enhanced_system = (
            f"{PERSONA}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "CONVERSATION CONTINUITY — READ THIS CAREFULLY\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "The CONVERSATION HISTORY below is YOUR ongoing dialogue with the user.\n"
            "It is listed in chronological order (oldest first, newest last).\n"
            "The most recent User message is the one you are now responding to.\n\n"
            "CRITICAL RULES:\n"
            "1. You MUST read the full history before responding.\n"
            "2. You are CONTINUING this conversation — not starting a new one.\n"
            "3. If a task or game is in progress (e.g. 20 questions, a list, a count),\n"
            "   reconstruct its current state from the history and continue from there.\n"
            "4. NEVER restart or re-introduce a task already in progress.\n"
            "5. NEVER ask questions already asked or answered in the history.\n"
            "6. Keep an accurate running count of anything being counted in the conversation.\n\n"
        )
        if memory_context:
            enhanced_system += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            enhanced_system += "CONVERSATION HISTORY & STORED KNOWLEDGE:\n"
            enhanced_system += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            enhanced_system += f"{memory_context}\n\n"
        else:
            enhanced_system += "No prior conversation history.\n\n"
        enhanced_system += (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Now respond to the latest User message, continuing naturally from where the conversation left off:\n"
        )

        try:
            # Use gguf_inference.generate with stream=True
            for chunk in gguf_inference.generate(
                prompt=user_input,
                system=enhanced_system,
                max_tokens=2048,
                temperature=config.get_temperature(),
                stream=True
            ):
                token = chunk.get("response", "")
                if token:
                    yield token
        except Exception as e:
            print(f"[COGNITIVE] Streaming error: {e}")
            yield f"I encountered an error while generating a response: {e}"

    def _stream_chat(self, user_input: str, args: dict, context: list) -> Generator[str, None, None]:
        """
        Stream a chat response for the given user input.
        """
        prompt = args.get("message") or user_input
        memory_context = self._retrieve_relevant_memories(user_input)
        yield from self._stream_chat_response(prompt, memory_context)

    def _learn_from_result(self, intent: Dict, result: Dict):
        action = intent.get("action")
        args = intent.get("args", {})
        if action == "OPEN_APP" and result.get("ok"):
            name = args.get("name")
            cmd = result.get("cmd")
            method = result.get("method")
            if name and cmd:
                self.memory.store_app_cmd(name, cmd, method)
                self.memory.log_habit_event("app_launch", {"app": name, "cmd": cmd, "method": method, "success": True})
        elif action == "OPEN_FILE_SYSTEM" and result.get("ok"):
            path = args.get("path")
            if path:
                self.memory.log_habit_event("dir_open", {"path": path})

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------
    def _start_reflection_loop(self):
        def loop():
            while self.running:
                time.sleep(24 * 3600)
                self._reflect()
        threading.Thread(target=loop, daemon=True).start()

    def _reflect(self):
        events = self.memory.get_habit_events(event_type="app_launch", days=1)
        apps = [e["data"].get("app") for e in events if e["data"].get("app")]
        from collections import Counter
        if apps:
            top = Counter(apps).most_common(3)
            insight = f"Today you used: {', '.join(f'{app} ({count}x)' for app, count in top)}"
            existing = self.memory.recall_memory("reflection", limit=5)
            if not any(insight in str(m.get("text", "")) for m in existing):
                self.memory.store_memory(insight, tags=["reflection", "daily"])
                print(f"[COGNITIVE] Reflection: {insight}")

    def _start_habit_loop(self):
        def loop():
            while self.running:
                time.sleep(12 * 3600)
                self._detect_habits()
        threading.Thread(target=loop, daemon=True).start()

    def _detect_habits(self):
        events = self.memory.get_habit_events(event_type="app_launch", days=7)
        hour_counts = {}
        for e in events:
            ts = e["timestamp"]
            hour = time.localtime(ts).tm_hour
            app = e["data"].get("app")
            key = (app, hour)
            hour_counts[key] = hour_counts.get(key, 0) + 1
        for (app, hour), count in hour_counts.items():
            if count >= 3:
                insight = f"You often open {app} around {hour}:00"
                self.memory.store_memory(insight, tags=["habit", "detected"])
                print(f"[COGNITIVE] Habit detected: {insight}")

    def _start_proactive_listener(self):
        try:
            from eli.brain.proactive_daemon import start_daemon
            self.proactive_daemon = start_daemon()
            self.add_observation("system", "Proactive daemon started")
            print("[COGNITIVE] Proactive daemon started – habit learning active")
        except Exception as e:
            print(f"[COGNITIVE] Failed to start proactive daemon: {e}")
            self.proactive_daemon = None

    def add_observation(self, source: str, content: str):
        self.memory.add_observation(source, content)


# ---------- SINGLETON EXPORT ----------
_engine = None
def get_engine():
    global _engine
    if _engine is None:
        _engine = CognitiveEngine()
    return _engine