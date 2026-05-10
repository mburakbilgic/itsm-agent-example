from __future__ import annotations

import re


class MarkdownChunker:
    """Splits a Markdown document into (section_heading, body) pairs.

    Sections start at `## ` headings. Lines before the first `## ` are
    grouped under the document's `# ` title (or "Overview").
    """

    _H1 = re.compile(r"^#\s+(.+)")
    _H2 = re.compile(r"^##\s+(.+)")

    def split(self, text: str) -> list[tuple[str, str]]:
        lines = text.splitlines()
        title_match = next((self._H1.match(line) for line in lines if line.startswith("# ")), None)
        title = title_match.group(1).strip() if title_match else "Overview"

        sections: list[tuple[str, list[str]]] = [(title, [])]
        for line in lines:
            m = self._H2.match(line)
            if m:
                sections.append((m.group(1).strip(), []))
            else:
                sections[-1][1].append(line)

        out: list[tuple[str, str]] = []
        for heading, body_lines in sections:
            body = "\n".join(body_lines).strip()
            if body:
                out.append((heading, body))
        return out
