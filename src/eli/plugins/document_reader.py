# eli/plugins/document_reader.py
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

class DocumentPlugin(Plugin):
    name = "documents"
    
    def __init__(self):
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        self.chroma = chromadb.Client()
        self.collection = self.chroma.create_collection("eli_docs")
    
    def ingest(self, path: str):
        # Extract text, chunk, embed, store
        chunks = self._extract_text(path)
        embeddings = self.embedder.encode(chunks)
        self.collection.add(embeddings, documents=chunks)
    
    def query(self, question: str) -> str:
        q_emb = self.embedder.encode([question])
        results = self.collection.query(q_emb, n_results=5)
        context = "\n".join(results['documents'][0])
        prompt = f"Answer based on:\n{context}\n\nQuestion: {question}"
        return chat_completion(prompt)
