"""Original paragraph/character chunker, retained for reproducible controls."""


def legacy_documents(row, size=1100):
    description = row.get("description", "")
    if not description.strip():
        return []
    header = "\n".join(f"{label}：{row.get(key, '')}" for label, key in (
        ("岗位", "title"), ("公司", "company"), ("地点", "location"),
        ("薪资", "salary"), ("经验", "experience"), ("学历", "education")))
    parts, buffer = [], ""
    for paragraph in description.splitlines(keepends=True):
        if buffer and len(buffer) + len(paragraph) > size:
            parts.append(buffer)
            buffer = ""
        while len(paragraph) > size:
            parts.append(paragraph[:size])
            paragraph = paragraph[size:]
        buffer += paragraph
    if buffer:
        parts.append(buffer)
    return [header + "\n\n" + part for part in parts]
