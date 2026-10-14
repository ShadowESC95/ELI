#!/usr/bin/env python3
"""
Advanced document generator - SIMPLE WORKING VERSION
"""

import os
import tempfile
from datetime import datetime

class AdvancedDocumentGenerator:
    """Generate actual documents with real content"""
    
    def __init__(self):
        pass
        
    def generate_document(self, topic, include_real_content=True):
        """Generate a document with real content"""
        
        clean_topic = topic.lower().strip()
        
        # Get content based on topic
        if 'quantum' in clean_topic and 'dot' in clean_topic:
            title = "Quantum Dots: Comprehensive Guide"
            content = self.get_quantum_dots_content()
        elif 'einstein' in clean_topic:
            title = "Albert Einstein: Life and Work"
            content = self.get_einstein_content()
        elif 'python' in clean_topic:
            title = "Python Programming Guide"
            content = self.get_python_content()
        elif 'ai' in clean_topic or 'artificial intelligence' in clean_topic:
            title = "Artificial Intelligence Guide"
            content = self.get_ai_content()
        elif 'linux' in clean_topic:
            title = "Linux Operating System Guide"
            content = self.get_linux_content()
        else:
            title = f"Comprehensive Guide: {topic.title()}"
            content = self.get_general_content(topic)
        
        # Create file
        return self.create_document_file(title, content, topic)
    
    def create_document_file(self, title, content, original_topic):
        """Create the actual document file"""
        try:
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_topic = "".join(c if c.isalnum() else "_" for c in original_topic[:30])
            filename = f"ELI_Advanced_{timestamp}_{safe_topic}.txt"
            filepath = os.path.join(temp_dir, filename)
            
            full_content = f"""ELI - Entropic Logical Interpreter
Advanced Document Generation System
========================================
DOCUMENT: {title}
TOPIC: {original_topic}
GENERATED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
========================================

{content}

========================================
END OF ADVANCED DOCUMENT
Generated automatically by ELI
========================================
"""
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(full_content)
            
            file_size = os.path.getsize(filepath)
            line_count = len(full_content.split('\n'))
            
            return {
                'success': True,
                'filepath': filepath,
                'filename': filename,
                'title': title,
                'size_kb': file_size / 1024,
                'lines': line_count,
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'generated_at': datetime.now().isoformat()
            }
    
    def get_quantum_dots_content(self):
        return """QUANTUM DOTS: COMPREHENSIVE GUIDE

INTRODUCTION
Quantum dots are nanoscale semiconductor particles with unique optical and electronic properties.

KEY PROPERTIES
• Size: 2-10 nanometers
• Composition: CdSe, InP, perovskite, etc.
• Quantum confinement effects
• Size-tunable fluorescence

APPLICATIONS
1. Display Technology - QLED TVs, wide color gamut
2. Biomedical Imaging - Fluorescent labels for cells
3. Solar Cells - Quantum dot photovoltaics
4. Quantum Computing - Qubit implementations
5. Sensors - Environmental and biological sensing

SYNTHESIS METHODS
• Colloidal synthesis (solution-based)
• Molecular beam epitaxy (high-quality crystals)
• Electrochemical methods
• Biological synthesis

CHARACTERIZATION
• TEM - Size and morphology
• XRD - Crystal structure
• UV-Vis - Absorption spectra
• PL - Photoluminescence properties

RECENT ADVANCES
• Non-toxic alternatives (InP, perovskites)
• Improved quantum yields (>90%)
• Commercial adoption in displays
• Biomedical applications expanding

CHALLENGES
• Toxicity concerns (heavy metals)
• Stability issues
• Scalable production
• Cost reduction needed

FUTURE OUTLOOK
Quantum dots are transforming display technology and enabling new applications in medicine, energy, and quantum computing.
"""
    
    def get_einstein_content(self):
        return """ALBERT EINSTEIN (1879-1955)

BIOGRAPHY
Albert Einstein was a German-born theoretical physicist who developed the theory of relativity.

MAJOR CONTRIBUTIONS
1. Special Relativity (1905) - E = mc²
2. General Relativity (1915) - Theory of gravitation
3. Photoelectric Effect (1905) - Nobel Prize 1921
4. Brownian Motion - Evidence for atoms
5. Quantum Theory - Key contributions

KEY ACHIEVEMENTS
• 1905: "Annus Mirabilis" papers
• 1915: General relativity completed
• 1921: Nobel Prize in Physics
• 1933: Moves to United States

PERSONAL LIFE
• Born: March 14, 1879, Ulm, Germany
• Died: April 18, 1955, Princeton, USA
• Education: Swiss Federal Polytechnic
• Family: Married twice, three children

FAMOUS QUOTES
"Imagination is more important than knowledge."
"The important thing is not to stop questioning."
"Science without religion is lame, religion without science is blind."

LEGACY
Einstein revolutionized physics and remains an icon of scientific genius.
"""
    
    def get_python_content(self):
        return """PYTHON PROGRAMMING GUIDE

INTRODUCTION
Python is a high-level, interpreted programming language known for its simplicity.

KEY FEATURES
• Simple, readable syntax
• Interpreted language
• Dynamic typing
• Extensive standard library
• Multi-paradigm support

BASIC SYNTAX
# Variables and data types
x = 10
name = "Python"
numbers = [1, 2, 3, 4, 5]

# Functions
def greet(name):
    return f"Hello, {name}!"

# Control flow
if x > 0:
    print("Positive")
else:
    print("Non-positive")

# Loops
for i in range(5):
    print(i)

DATA STRUCTURES
• Lists: [1, 2, 3] - Mutable, ordered
• Tuples: (1, 2, 3) - Immutable, ordered
• Dictionaries: {"key": "value"} - Key-value pairs
• Sets: {1, 2, 3} - Unique elements
• Strings: "text" - Immutable text

OBJECT-ORIENTED PROGRAMMING
class Dog:
    def __init__(self, name, age):
        self.name = name
        self.age = age
    
    def bark(self):
        return "Woof!"
    
    def description(self):
        return f"{self.name} is {self.age} years old"

POPULAR LIBRARIES
• Web: Django, Flask, FastAPI
• Data Science: NumPy, pandas, Matplotlib
• ML: TensorFlow, PyTorch, scikit-learn
• GUI: Tkinter, PyQt
• Testing: pytest, unittest

BEST PRACTICES
1. Follow PEP 8 style guide
2. Use virtual environments
3. Write docstrings
4. Handle exceptions properly
5. Use version control (Git)

CAREER PATHS
• Python Developer ($90-130K)
• Data Scientist ($100-150K)
• DevOps Engineer ($110-160K)
• ML Engineer ($120-180K)

LEARNING RESOURCES
• Official: Python.org
• Learning: Real Python, Codecademy
• Books: "Python Crash Course"
• Community: Python Discord
"""
    
    def get_ai_content(self):
        return """ARTIFICIAL INTELLIGENCE GUIDE

OVERVIEW
AI enables machines to perform tasks requiring human intelligence.

HISTORY
1956: Dartmouth Conference coins term "AI"
1960s: Early AI programs
1980s: Expert systems
1990s: Machine learning resurgence
2010s: Deep learning revolution
2020s: Large language models

TYPES OF AI
1. Narrow AI - Specific tasks (current)
2. General AI - Human-level intelligence (future)
3. Superintelligence - Beyond human intelligence

MACHINE LEARNING APPROACHES
• Supervised Learning - Labeled data
• Unsupervised Learning - Unlabeled data
• Reinforcement Learning - Trial and error
• Deep Learning - Neural networks

KEY TECHNOLOGIES
1. Natural Language Processing (NLP)
2. Computer Vision
3. Robotics
4. Expert Systems

APPLICATIONS
• Healthcare: Diagnosis, drug discovery
• Finance: Fraud detection, trading
• Transportation: Autonomous vehicles
• Education: Personalized learning
• Entertainment: Recommendations

ETHICAL CONSIDERATIONS
• Bias and fairness
• Privacy and security
• Job displacement
• AI safety and alignment

FUTURE TRENDS
• Multimodal AI
• Neurosymbolic AI
• Edge AI
• Quantum machine learning

LEARNING RESOURCES
• Books: "AI: A Modern Approach"
• Courses: Andrew Ng's ML on Coursera
• Frameworks: TensorFlow, PyTorch
"""
    
    def get_linux_content(self):
        return """LINUX OPERATING SYSTEM GUIDE

INTRODUCTION
Linux is an open-source Unix-like operating system based on the Linux kernel.

HISTORY
1991: Linus Torvalds begins development
1992: Licensed under GPL
1993: First distributions
2000s: Enterprise adoption
Present: Powers most servers and Android

DISTRIBUTIONS
• Debian-based: Ubuntu, Mint
• Red Hat-based: Fedora, RHEL
• Arch-based: Arch, Manjaro
• Others: openSUSE, Slackware

FILE SYSTEM
/       - Root
/bin    - Binaries
/etc    - Configuration
/home   - User homes
/usr    - Programs
/var    - Variable data
/tmp    - Temporary files

ESSENTIAL COMMANDS
ls      - List files
cd      - Change directory
cp      - Copy
mv      - Move/rename
rm      - Remove
mkdir   - Create directory
rmdir   - Remove directory
cat     - Concatenate files
grep    - Search text
chmod   - Change permissions
sudo    - Superuser do

PACKAGE MANAGEMENT
Debian/Ubuntu: apt
  sudo apt update
  sudo apt install package
  sudo apt remove package

Red Hat/Fedora: dnf
  sudo dnf install package
  sudo dnf update
  sudo dnf remove package

Arch: pacman
  sudo pacman -Syu
  sudo pacman -S package
  sudo pacman -R package

SHELL SCRIPTING
#!/bin/bash
echo "Hello, World!"

# Variables
name="Linux"
echo "Welcome to $name"

# Conditionals
if [ -f file.txt ]; then
    echo "File exists"
else
    echo "File not found"
fi

# Loops
for i in {1..5}; do
    echo "Number: $i"
done

SYSTEM ADMINISTRATION
• User management: useradd, passwd, usermod
• Service management: systemctl
• Log management: journalctl, tail -f
• Disk management: df, du, mount

SECURITY
• Regular updates
• Strong passwords
• SSH key authentication
• Firewall configuration
• Regular backups

CAREER PATHS
• Linux Admin ($70-120K)
• DevOps Engineer ($100-160K)
• SRE ($120-180K)
• Security Engineer ($90-150K)

LEARNING RESOURCES
• man pages (manual)
• TLDP (The Linux Documentation Project)
• Arch Wiki (excellent resource)
• Linux Foundation courses
"""
    
    def get_general_content(self, topic):
        return f"""COMPREHENSIVE GUIDE: {topic.upper()}

INTRODUCTION
This document provides detailed information about {topic}, generated by ELI's document generator.

KEY AREAS TO EXPLORE

1. HISTORICAL BACKGROUND
   • Origins and early development
   • Key historical milestones
   • Evolution over time

2. FUNDAMENTAL CONCEPTS
   • Core principles and theories
   • Key terminology and definitions
   • Foundational knowledge

3. MAJOR CONTRIBUTORS
   • Influential figures in the field
   • Their significant contributions
   • Current thought leaders

4. PRACTICAL APPLICATIONS
   • Real-world uses and implementations
   • Industry applications
   • Everyday relevance

5. CURRENT TRENDS
   • Latest developments and research
   • Emerging technologies
   • Future directions

6. LEARNING PATH
   • Recommended study materials
   • Essential skills to develop
   • Career opportunities

DETAILED ANALYSIS
For comprehensive understanding of {topic}, consider exploring:

THEORETICAL FOUNDATIONS
• Underlying principles and theories
• Mathematical or conceptual frameworks
• Key models and paradigms

TECHNICAL ASPECTS
• Tools and technologies used
• Methodologies and approaches
• Best practices and standards

PRACTICAL IMPLEMENTATIONS
• Real-world case studies
• Success stories and examples
• Common challenges and solutions

FUTURE DEVELOPMENTS
• Research frontiers
• Emerging trends
• Potential breakthroughs

RESOURCES FOR FURTHER STUDY

BOOKS AND PUBLICATIONS
• Foundational texts
• Recent research papers
• Industry reports

ONLINE RESOURCES
• Educational websites
• Video tutorials and courses
• Professional forums

ORGANIZATIONS AND COMMUNITIES
• Professional associations
• Research institutions
• Online communities

ACTIONABLE STEPS
1. Start with foundational knowledge
2. Practice with hands-on projects
3. Connect with experts in the field
4. Stay updated with latest developments
5. Apply knowledge to real problems

CONCLUSION
{topic.title()} represents an important field with diverse applications and significant potential for future development. Continued learning and practical application will lead to deeper understanding and potential contributions to the field.
"""

if __name__ == "__main__":
    generator = AdvancedDocumentGenerator()
    result = generator.generate_document("quantum dots")
    print(f"Test: {result['success']}, File: {result['filename']}")


# ============================
# Ollama-backed longform generation
# ============================

    import os
    import requests

    def _ollama_host() -> str:
        from eli.brain import config as eli_config
        return eli_config.ollama_base()

    def generate_with_ollama(topic: str,
                             model: str = None,
                             target_words: int = 1800,
                             style_hint: str = "",
                             citations: bool = False,
                             stream: bool = False):
        """Generate a long-form markdown document using Ollama /api/chat.
        Returns (text, meta). If stream=True, returns (generator, meta) where generator yields chunks.
        """
        from eli.brain import config as eli_config
        model = (model or eli_config.ollama_model()).strip()
        if not model:
            raise ValueError("no Ollama model set (ELI_MODEL)")
        topic = (topic or "").strip()
        if not topic:
            raise ValueError("topic required")

        # Keep prompt deterministic-ish: request structure + length.
        # We avoid web citations here; if you want citations, wire a web fetch step before calling.
        prompt = f"""Write a detailed, technically accurate document about: {topic}

Requirements:
- Use markdown headings.
- Length target: ~{target_words} words minimum (more is fine).
- Include: overview, historical context, key concepts, equations (if relevant), examples, misconceptions, and a short FAQ.
- Be rigorous and avoid hallucinating specifics; if uncertain, say so explicitly.
{('' if not citations else '- Include a references section with source names/urls if you can verify them.')}
Style:
{style_hint or 'Direct, nerdy, brutally honest. No fluff.'}
"""

        payload = {
            "model": model,
            "stream": bool(stream),
            "messages": [
                {"role": "system", "content": "You are ELI (Entropy Logical Interface): the user's brutally honest, nerdy research partner. Prioritize correctness over confidence."},
                {"role": "user", "content": prompt},
            ],
        }

        host = _ollama_host()
        url = host + "/api/chat"

        if not stream:
            r = requests.post(url, json=payload, timeout=900)
            r.raise_for_status()
            data = r.json()
            text = (data.get("message") or {}).get("content") or ""
            meta = {
                "model": data.get("model"),
                "total_duration": data.get("total_duration"),
                "eval_count": data.get("eval_count"),
            }
            return text, meta

        # Streaming: Ollama returns ndjson lines
        def _gen():
            with requests.post(url, json=payload, stream=True, timeout=600) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        j = json.loads(line)
                    except Exception:
                        continue
                    msg = (j.get("message") or {}).get("content")
                    if msg:
                        yield msg
        return _gen(), {"model": model}
# ============================================================
# LLM-backed document generation (Ollama) — injected API
# ============================================================
def generate_document(topic: str,
                      format: str = "md",
                      detail: str = "detailed",
                      model: str | None = None,
                      ollama_host: str | None = None) -> str:
    """
    Generate a real document using local Ollama. Returns markdown text.

    Defaults:
      model: ELI_CHAT_MODEL -> ELI_MODEL -> OLLAMA_MODEL
      host:  ELI_OLLAMA_HOST -> OLLAMA_BASE_URL -> OLLAMA_HOST -> http://127.0.0.1:11434
    """
    import os
    import requests

    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic is required")

    from eli.brain import config as eli_config
    host = (ollama_host or eli_config.ollama_base()).rstrip("/")
    mdl = model or eli_config.ollama_model()
    if not mdl:
        raise ValueError("no Ollama model set (ELI_MODEL)")

    fmt = (format or "md").strip().lower()
    if fmt not in ("md", "markdown"):
        fmt = "md"

    sys = (
        "You are ELI's document generator. Produce a COMPLETE document (not a scaffold).\n"
        "Output rules:\n"
        "- Output only the final document content.\n"
        "- Use Markdown headings.\n"
        "- Prefer correctness over hype.\n"
        "- If uncertain about a claim, say so plainly.\n"
        "- Include a short 'Sources / verification notes' section listing source TYPES (books, papers, etc.).\n"
    )

    user = (
        f"Write a {detail} document about: {topic}\n\n"
        "Include sections:\n"
        "## Summary\n"
        "## Key points\n"
        "## Short timeline\n"
        "## Why it matters\n"
        "## Common misconceptions\n"
        "## Further questions\n"
        "## Sources / verification notes\n"
    )

    payload = {
        "model": mdl,
        "stream": False,
        "messages": [
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0.4},
    }

    r = requests.post(f"{host}/api/chat", json=payload, timeout=180)
    r.raise_for_status()
    j = r.json() or {}
    content = ((j.get("message") or {}).get("content") or "").strip()

    if not content:
        raise RuntimeError("Ollama returned empty content")
    return content


def write_document(topic: str,
                   out_path: str,
                   format: str = "md",
                   detail: str = "detailed") -> str:
    """
    Generate and write a document to disk. Returns out_path.
    """
    from pathlib import Path
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_document(topic, format=format, detail=detail), encoding="utf-8")
    return str(out)
