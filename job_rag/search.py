import math
import re
from collections import Counter

from pydantic import BaseModel, Field
from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select

from .db import Chunk, Job
from .models import chat, embed


class SearchRequest(BaseModel):
    query: str = Field(default="", max_length=2000)
    city: str | None = None
    district: str | None = None
    min_salary: float | None = Field(default=None, ge=0)
    max_salary: float | None = Field(default=None, ge=0)
    salary_period: str = Field(default="month", pattern="^(month|day|hour)$")
    salary_mode: str = Field(default="lower_bound", pattern="^(lower_bound|overlap)$")
    experience_years: float | None = Field(default=None, ge=0, le=60)
    education: str | None = None
    employment_type: str | None = Field(default=None, pattern="^(internship|unknown)$")
    skills: list[str] = Field(default_factory=list, max_length=20)
    active_only: bool = False
    include_closed: bool = False
    limit: int = Field(default=8, ge=1, le=30)
    generate: bool = False
    infer_filters: bool = True


def resolve_filters(request, cities):
    """Only conservative, explicit patterns; UI filters override heuristic extraction."""
    if not request.infer_filters:
        return request
    data = request.model_dump()
    query = request.query
    if not data["city"]:
        matches = [city for city in cities if city and city in query]
        if len(matches) == 1:
            data["city"] = matches[0]
    if data["min_salary"] is None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*[kK]\s*(?:以上|起|及以上)", query)
        if match:
            data["min_salary"] = float(match[1]) * 1000
    if data["experience_years"] is None:
        match = re.search(r"(?:我有|具有|拥有)?(\d+)年(?:工作)?经验", query)
        if match:
            data["experience_years"] = float(match[1])
    return SearchRequest(**data)


def tokens(text):
    text = text.lower()
    # These aliases improve exact retrieval, not a substitute for semantic embeddings.
    text = text.replace("大语言模型", "大模型").replace("llm", "大模型 llm")
    output = re.findall(r"[a-z][a-z0-9+#.]*", text)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            continue
        output.extend(run[i:i + 2] for i in range(len(run) - 1))
    stop = {"岗位", "职位", "招聘", "工作", "公司", "经验", "以上", "以下", "要求", "哪些", "有没有", "有哪", "推荐", "帮我", "寻找", "适合", "相关", "需要", "接受", "薪资", "月薪", "年经"}
    return [token for token in output if token not in stop]


def bm25(query_tokens, texts):
    bags = [Counter(tokens(text)) for text in texts]
    average = sum(sum(bag.values()) for bag in bags) / max(len(bags), 1) or 1
    frequencies = Counter(token for bag in bags for token in bag)
    scores = []
    for bag in bags:
        length, score = sum(bag.values()), 0.0
        for token in set(query_tokens):
            count = bag[token]
            if count:
                idf = math.log(1 + (len(bags) - frequencies[token] + .5) / (frequencies[token] + .5))
                score += idf * count * 2.2 / (count + 1.2 * (.25 + .75 * length / average))
        scores.append(score)
    return scores


def matches(job, filters):
    norm = job.normalized
    if filters.city and norm["city"] != filters.city:
        return False
    if filters.district and norm["district"] != filters.district:
        return False
    if filters.min_salary is not None or filters.max_salary is not None:
        if norm["salary_period"] != filters.salary_period or norm["salary_min"] is None:
            return False
        if filters.min_salary is not None:
            bound = norm["salary_min"] if filters.salary_mode == "lower_bound" else norm["salary_max"]
            if bound < filters.min_salary:
                return False
        if filters.max_salary is not None and norm["salary_min"] > filters.max_salary:
            return False
    if filters.experience_years is not None:
        if norm["experience_min"] is None or norm["experience_min"] > filters.experience_years:
            return False
    if filters.education and norm["education_level"] != filters.education:
        return False
    if filters.employment_type and norm["employment_type"] != filters.employment_type:
        return False
    # Explicit skills are hard constraints; query text is a relevance signal.
    source_text = (job.raw["title"] + "\n" + job.raw["description"]).lower()
    for skill in filters.skills:
        skill = skill.strip().lower()
        if not skill:
            continue
        if re.fullmatch(r"[a-z0-9+#.]+", skill):
            if not re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", source_text):
                return False
        elif skill not in source_text:
            return False
    return True


def serialize(job, detail=False):
    result = {key: job.raw.get(key, "") for key in (
        "title", "company", "location", "salary", "experience", "education", "url", "collected_at")}
    result.update(key=job.key, source=job.source, job_id=job.job_id,
                  job_status=job.job_status, status_reason=job.status_reason,
                  last_verified_at=job.last_verified_at, last_seen_at=job.last_seen_at,
                  first_seen_at=job.first_seen_at, version=job.version,
                  indexed_version=job.indexed_version, normalized=job.normalized,
                  collection_status=job.raw.get("status", ""))
    if detail:
        result["raw"] = job.raw
    return result


def search(db, settings, request):
    warnings = []
    with db.session() as session:
        all_jobs = list(session.scalars(select(Job)))
        filters = resolve_filters(request, {j.normalized["city"] for j in all_jobs})
        jobs = {j.key: j for j in all_jobs if matches(j, filters)
                and (j.job_status == "active" if filters.active_only else
                     (filters.include_closed or j.job_status in {"active", "unknown"}))
                and j.indexed_version == j.version and j.index_signature == settings.index_signature}
        chunks = list(session.scalars(select(Chunk).join(Job, Chunk.job_key == Job.key).where(
            Chunk.version == Job.version, Job.indexed_version == Job.version,
            Job.index_signature == settings.index_signature)))
        chunks = [chunk for chunk in chunks if chunk.job_key in jobs]
        query = filters.query
        for value in [filters.city, filters.district]:
            if value:
                query = query.replace(value, " ")
        query = re.sub(r"\d+(?:\.\d+)?\s*[kK]\s*(?:以上|起|及以上)", " ", query)
        query = re.sub(r"(?:我有|具有|拥有)?\d+年(?:工作)?经验", " ", query)
        query_terms = tokens(query)
        scores = bm25(query_terms, [c.text for c in chunks])
        lexical = sorted((i for i, score in enumerate(scores) if score > 0), key=lambda i: scores[i], reverse=True)
        semantic = []
        mode = "keyword"
        if settings.semantic_enabled and query.strip() and chunks:
            try:
                vector = embed(settings, [filters.query], text_type="query")[0]
                if db.engine.dialect.name == "postgresql":
                    # Exact pgvector distance; an ANN index is unnecessary for this small corpus.
                    distance = cast(Chunk.embedding, Vector()).cosine_distance(vector)
                    ranked_ids = list(session.scalars(select(Chunk.id).join(Job, Chunk.job_key == Job.key).where(
                        Chunk.embedding.is_not(None), Chunk.version == Job.version,
                        Job.indexed_version == Job.version, Job.index_signature == settings.index_signature
                    ).order_by(distance)))
                    positions = {chunk.id: i for i, chunk in enumerate(chunks)}
                    semantic = [positions[chunk_id] for chunk_id in ranked_ids if chunk_id in positions]
                else:
                    def similarity(i):
                        other = chunks[i].embedding
                        return sum(a * b for a, b in zip(vector, other)) / (math.sqrt(sum(x*x for x in vector)) * math.sqrt(sum(x*x for x in other)))
                    semantic = sorted((i for i, c in enumerate(chunks) if c.embedding is not None), key=similarity, reverse=True)
                mode = "hybrid"
            except Exception:
                warnings.append("语义服务不可用，已降级为关键词检索。")
        combined = Counter()
        for ranking in [lexical, semantic]:
            for rank, index in enumerate(ranking[:100]):
                combined[index] += 1 / (60 + rank + 1)
        if not query_terms and not semantic:
            combined.update({i: 1 for i in range(len(chunks))})
            mode = "filter"
        ranked = sorted(combined, key=lambda i: (-combined[i], chunks[i].job_key, chunks[i].ordinal))
        grouped = {}
        for index in ranked:
            chunk = chunks[index]
            if chunk.job_key not in grouped:
                grouped[chunk.job_key] = {**serialize(jobs[chunk.job_key]), "score": round(combined[index], 6),
                                          "evidence": [], "evidence_chunk_ids": [], "evidence_details": []}
            if len(grouped[chunk.job_key]["evidence"]) < 2:
                grouped[chunk.job_key]["evidence"].append(chunk.text)
                grouped[chunk.job_key]["evidence_chunk_ids"].append(chunk.id)
                grouped[chunk.job_key]["evidence_details"].append(chunk.details or {"section_type": "unknown", "requirement_level": "unspecified"})
        results = list(grouped.values())[:filters.limit]
        from .chunking import parse_sections
        for result in results:
            description = jobs[result["key"]].raw["description"]
            context, remaining = [], 3600
            for section in parse_sections(description):
                if section.section_type not in {"requirements", "preferred"} or not description[section.start:section.end].strip():
                    continue
                end = min(section.end, section.start + remaining)
                context.append({"section_type": section.section_type, "title": section.title,
                                "text": description[section.start:end], "source_start": section.start,
                                "source_end": end, "truncated": end < section.end})
                remaining -= end - section.start
                if remaining <= 0:
                    break
            result["qualification_context"] = context
        if any(j.indexed_version != j.version or j.index_signature != settings.index_signature for j in all_jobs):
            warnings.append("部分岗位索引尚未就绪；请运行 worker 或 reindex。旧版本不参与检索。")
        if any(r["job_status"] != "active" for r in results):
            warnings.append("结果含未确认在招或历史岗位，采集成功不代表目前仍在招聘。")
        return {"results": results, "total_matched": len(grouped), "mode": mode,
                "filters": filters.model_dump(exclude={"generate"}), "warnings": warnings}


def answer(db, settings, request):
    result = search(db, settings, request)
    sources = result["results"]
    result["answer_mode"] = "extractive"
    if not sources:
        result["answer"] = "未找到满足条件的岗位。可放宽筛选条件；这不代表市场上不存在此类岗位。"
        return result
    labels = {"active": "已确认在招", "unknown": "未核验", "closed": "已关闭", "suspected_expired": "疑似失效"}
    lines = ["以下是候选岗位，请结合原招聘页面确认最新信息："]
    for i, item in enumerate(sources, 1):
        lines.append(f"[{i}] {item['title']}｜{item['company']}｜{item['salary']}｜{item['location']}；"
                     f"状态：{labels[item['job_status']]}，采集于 {item['collected_at']}。")
    result["answer"] = "\n".join(lines)
    if request.generate and settings.chat_api_key and settings.chat_model:
        try:
            generated = chat(settings, request.query, sources)
            citations = re.findall(r"\[(\d+)\]", generated)
            if not citations or any(not 1 <= int(citation) <= len(sources) for citation in citations):
                raise ValueError("Missing or invalid citations")
            result["answer"] = generated
            result["answer_mode"] = "llm"
        except Exception:
            result["warnings"].append("生成服务不可用，已返回可核对的岗位列表。")
    elif request.generate:
        result["warnings"].append("未配置生成模型，当前为来源列表，不是大模型生成回答。")
    # A model request can take seconds. Never return a source changed/closed during generation.
    with db.session() as session:
        for item in sources:
            current = session.get(Job, item["key"])
            if current is None or current.version != item["version"] or current.job_status != item["job_status"]:
                result["results"] = []
                result["total_matched"] = 0
                result["answer_mode"] = "extractive"
                result["answer"] = "岗位在检索期间发生更新，请重新查询以获取最新结果。"
                result["warnings"].append("已拦截过期结果。")
                break
    return result
