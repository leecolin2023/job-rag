import argparse
import json
from pathlib import Path

from .config import Settings
from .db import Database
from .ingest import import_csv, reindex, run_index_tasks, set_status
from .search import SearchRequest, answer


def main():
    parser = argparse.ArgumentParser(description="Job-RAG 知识库管理")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="初始化数据库")
    ingest = sub.add_parser("import", help="增量导入 CSV；默认同步执行索引任务")
    ingest.add_argument("path")
    ingest.add_argument("--source", default="boss")
    ingest.add_argument("--no-index", action="store_true")
    sub.add_parser("worker", help="执行一次待处理/失败索引任务，可重复运行")
    sub.add_parser("reindex", help="用当前模型配置重建索引")
    status = sub.add_parser("status", help="根据核验依据变更岗位状态")
    status.add_argument("job_id")
    status.add_argument("state", choices=["unknown", "active", "suspected_expired", "closed"])
    status.add_argument("--reason", required=True)
    status.add_argument("--source", default="boss")
    search = sub.add_parser("search", help="查询知识库")
    search.add_argument("query")
    search.add_argument("--city")
    search.add_argument("--min-salary", type=float)
    search.add_argument("--skills", nargs="*", default=[])
    search.add_argument("--active-only", action="store_true")
    search.add_argument("--generate", action="store_true")
    serve = sub.add_parser("serve", help="启动网页和 API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        uvicorn.run("job_rag.api:app", host=args.host, port=args.port)
        return
    settings = Settings()
    db = Database(settings)
    db.initialize()
    result = {"ok": True}
    try:
        if args.command == "import":
            result = import_csv(db, settings, Path(args.path).read_bytes(), args.source)
            if not args.no_index:
                result["index"] = run_index_tasks(db, settings)
        elif args.command == "worker":
            result = run_index_tasks(db, settings)
        elif args.command == "reindex":
            result = reindex(db, settings)
        elif args.command == "status":
            set_status(db, f"{args.source}:{args.job_id}", args.state, args.reason)
        elif args.command == "search":
            result = answer(db, settings, SearchRequest(query=args.query, city=args.city,
                            min_salary=args.min_salary, skills=args.skills,
                            active_only=args.active_only, generate=args.generate))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("failed", 0) or result.get("index", {}).get("failed", 0):
            raise SystemExit(1)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"错误：{exc}\n")
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
