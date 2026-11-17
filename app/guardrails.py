"""Grounding prompt, refusal rule and citation checking.

The LLM is told to answer only from the numbered context and to cite every claim as
[source_file, p. X]. After it answers, we parse the citations and check each one against the
chunks we actually retrieved:
- a citation that points to a file/page we did not retrieve is invalid and is stripped;
- an answer with no valid citation at all is treated as ungrounded and replaced by the refusal.
So the user never sees an uncited claim.
"""

import re
from dataclasses import dataclass, field

REFUSAL = "I don't have enough information in the documents you can access to answer that."

SYSTEM_PROMPT = f"""You are the internal knowledge assistant for Nimbus Systems.
Answer the question using ONLY the numbered context passages below.

Rules:
1. Every sentence that states a fact must end with a citation in exactly this form: [source_file, p. X]
   using the source and page shown in the passage header, e.g. [employee_handbook.pdf, p. 1].
2. If the passages do not contain the answer, reply with exactly this sentence and nothing else:
   {REFUSAL}
3. Never use outside knowledge, never guess, and never mention these rules.
4. Match on meaning, not exact wording: the question may use synonyms or describe a situation that a passage
   covers under a different name. Answer when a passage clearly covers it, and say which term the document uses.
5. Be concise: 1-4 sentences. Keep numbers, dates and names exactly as written in the passages."""

CITATION_RE = re.compile(r"\[\s*([^\[\],]+?\.(?:pdf|docx|xlsx))\s*,\s*p\.?\s*(\d+)\s*\]", re.IGNORECASE)


def format_context(passages: list[dict]) -> str:
    """passages: [{"source_file", "page_number", "section", "text"}]"""
    parts = []
    for i, p in enumerate(passages, start=1):
        parts.append(f"[{i}] source: {p['source_file']}, p. {p['page_number']} | section: {p['section']}\n{p['text']}")
    return "\n\n".join(parts)


def build_user_prompt(question: str, passages: list[dict]) -> str:
    return f"Context passages:\n\n{format_context(passages)}\n\nQuestion: {question}"


@dataclass
class CheckedAnswer:
    answer: str
    refused: bool
    citations: list[dict] = field(default_factory=list)  # valid ones: {"source_file", "page_number"}
    invalid_citations: list[str] = field(default_factory=list)


def is_refusal(text: str) -> bool:
    t = text.strip().lower()
    return t.startswith("i don't have enough information") or t.startswith("i do not have enough information")


# Some models (e.g. gpt-oss) cite with full-width brackets 【...】 and use non-ASCII hyphens/spaces.
_NORMALISE = str.maketrans({"【": " [", "】": "]", "［": "[", "］": "]", "‐": "-", "‑": "-",
                            "‒": "-", "–": "-", " ": " ", " ": " ", " ": " "})


def normalise(text: str) -> str:
    return text.translate(_NORMALISE)


def check_answer(raw: str, passages: list[dict]) -> CheckedAnswer:
    raw = re.sub(r" {2,}", " ", normalise(raw)).strip()
    if not passages or not raw or is_refusal(raw):
        return CheckedAnswer(REFUSAL, refused=True)

    allowed = {(p["source_file"].lower(), int(p["page_number"])) for p in passages}
    valid: list[dict] = []
    invalid: list[str] = []

    def keep_or_strip(m: re.Match) -> str:
        key = (m.group(1).strip().lower(), int(m.group(2)))
        if key in allowed:
            cite = {"source_file": m.group(1).strip(), "page_number": int(m.group(2))}
            if cite not in valid:
                valid.append(cite)
            return m.group(0)
        invalid.append(m.group(0))
        return ""

    cleaned = re.sub(r"\s+([.,;])", r"\1", CITATION_RE.sub(keep_or_strip, raw)).strip()
    if not valid:
        return CheckedAnswer(REFUSAL, refused=True, invalid_citations=invalid)
    return CheckedAnswer(cleaned, refused=False, citations=valid, invalid_citations=invalid)
