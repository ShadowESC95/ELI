
# chat_stream.py — streaming token backend

def stream_response(llm, prompt, metadata=None):
    metadata = metadata or {}
    for token in llm.generate_stream(prompt):
        yield {
            "type": "token",
            "value": token
        }
    yield {
        "type": "end",
        "tts_available": True,
        "authority": metadata.get("authority", "normal")
    }
