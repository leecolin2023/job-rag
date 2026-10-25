"""Conservative normalization: derived fields never overwrite source text."""
import hashlib
import json
import re
import unicodedata

REQUIRED_COLUMNS = {
    "job_id", "title", "company", "location", "salary", "experience", "education",
    "url", "description", "status", "collected_at",
}
CONTENT_FIELDS = ("title", "company", "location", "salary", "experience", "education", "description", "address", "url")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def normalize(row):
    salary = unicodedata.normalize("NFKC", row.get("salary", ""))
    result = {"city": row.get("location", "").split("·")[0], "district": None,
              "salary_min": None, "salary_max": None, "salary_period": "unknown",
              "salary_months": None, "experience_min": None, "experience_max": None,
              "education_level": None, "employment_type": "unknown", "quality_flags": []}
    location_parts = row.get("location", "").split("·")
    if len(location_parts) > 1:
        result["district"] = location_parts[1]
    match = re.search(r"(\d+(?:\.\d+)?)\s*[-~至]\s*(\d+(?:\.\d+)?)\s*[Kk]", salary)
    if match:
        result.update(salary_min=float(match[1]) * 1000, salary_max=float(match[2]) * 1000, salary_period="month")
    else:
        match = re.search(r"(\d+(?:\.\d+)?)\s*[-~至]\s*(\d+(?:\.\d+)?)\s*元\s*/\s*(天|小时|时)", salary)
        if match:
            result.update(salary_min=float(match[1]), salary_max=float(match[2]), salary_period="day" if match[3] == "天" else "hour")
    months = re.search(r"(\d+)薪", salary)
    if months:
        result["salary_months"] = int(months[1])
    experience = row.get("experience", "")
    years = re.search(r"(\d+)\s*[-~至]\s*(\d+)年", experience)
    if years:
        result.update(experience_min=int(years[1]), experience_max=int(years[2]))
    elif re.search(r"(\d+)年以上", experience):
        result["experience_min"] = int(re.search(r"(\d+)年以上", experience)[1])
    elif "经验不限" in experience or "在校/应届" in experience:
        result["experience_min"] = 0
    if "/周" in experience or "实习" in row.get("title", ""):
        result["employment_type"] = "internship"
    education = row.get("education", "")
    if education in {"博士", "硕士", "本科", "大专", "高中", "中专", "学历不限"}:
        result["education_level"] = education
    if not row.get("description", "").strip():
        result["quality_flags"].append("missing_description")
    if "页面未显示" in " ".join(row.values()):
        result["quality_flags"].append("source_fields_unknown")
    if "学历" in experience:
        result["quality_flags"].append("mixed_experience_field")
    if result["salary_min"] is None:
        result["quality_flags"].append("salary_not_comparable")
    return result


def content_hash(row):
    return digest({k: row.get(k, "") for k in CONTENT_FIELDS})


def legacy_documents(row, size=1100):
    """Keep a job boundary and original paragraph text; prepend identifying context."""
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


def documents(row, size=1100):
    """Compatibility text-only facade over the source-aligned structured parser."""
    from .chunking import build_documents
    return [document.text for document in build_documents(row, size=size)]
