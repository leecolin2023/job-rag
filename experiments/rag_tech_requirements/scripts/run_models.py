"""Run real configured Embedding -> hybrid recall -> rerank -> built-in generation.

Uses an isolated DB and logs real provider response IDs/usage without credentials.
No mock transport, generated vectors, or silent acceptance of fallbacks.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import httpx
from dotenv import dotenv_values
from sqlalchemy import func, select
from job_rag.config import Settings
from job_rag.storage import Database, Chunk
from job_rag.preprocessing.importer import import_csv
from job_rag.indexing.worker import run_index_tasks
from job_rag.retrieval.answer import answer
from job_rag.retrieval.search import SearchRequest
from job_rag.querying.get_knowledge_base_stats import knowledge_base_stats


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output
    values = dotenv_values('.env.experiments')
    required = ['BAILIAN_API_HOST', 'BAILIAN_API_KEY', 'BAILIAN_EMBEDDING_MODEL', 'BAILIAN_RERANK_MODEL']
    if any(not values.get(k) for k in required):
        raise ValueError('Existing Bailian configuration incomplete')
    host = values['BAILIAN_API_HOST'].rstrip('/')
    settings = Settings(database_url='sqlite:///' + str((output / 'models.db').resolve()),
        embedding_base_url=host + '/api/v1', embedding_api_key=values['BAILIAN_API_KEY'],
        embedding_model=values['BAILIAN_EMBEDDING_MODEL'], embedding_dimensions=int(values['BAILIAN_EMBEDDING_DIMENSIONS']),
        embedding_api_format='dashscope', embedding_batch_size=20,
        rerank_base_url=host + '/api/v1', rerank_api_key=values['BAILIAN_API_KEY'],
        rerank_model=values['BAILIAN_RERANK_MODEL'],
        chat_base_url=host + '/compatible-mode/v1', chat_api_key=values['BAILIAN_API_KEY'], chat_model='qwen-plus',
        chat_timeout_seconds=180,
        admin_token='')
    events = []
    original_client = httpx.Client
    def record_response(response):
        request = response.request
        if not any(p in request.url.path for p in ['text-embedding', 'text-rerank', 'chat/completions']):
            return
        response.read()
        body = response.json() if response.headers.get('content-type','').startswith('application/json') else {}
        payload = json.loads(request.content)
        event = {'time': datetime.now(timezone.utc).isoformat(), 'operation': request.url.path,
                 'model': payload.get('model'), 'status': response.status_code,
                 'request_id': body.get('request_id', body.get('id')),
                 'usage': body.get('usage'), 'payload_sha256': hashlib.sha256(request.content).hexdigest(),
                 'latency_ms': round((time.monotonic() - request.extensions['model_started_at']) * 1000, 2)}
        if 'text-embedding' in request.url.path:
            event.update(text_type=payload['parameters']['text_type'], inputs=len(payload['input']['texts']))
        if 'text-rerank' in request.url.path:
            event['documents'] = len(payload['input']['documents'])
        events.append(event)
        with (output / 'provider_calls.jsonl').open('a') as f:
            f.write(json.dumps(event,ensure_ascii=False) + '\n')
        if len(events) % 25 == 0:
            print(json.dumps({'provider_calls_this_process':len(events), 'last_status':response.status_code}), flush=True)
    def record_request(request):
        if any(p in request.url.path for p in ['text-embedding', 'text-rerank', 'chat/completions']):
            if len(events) >= 1500:
                raise RuntimeError('Real model request limit reached')
            request.extensions['model_started_at'] = time.monotonic()
    class AuditedClient(original_client):
        def __init__(self, *a, **kw):
            hooks = kw.setdefault('event_hooks', {})
            hooks['request'] = list(hooks.get('request', [])) + [record_request]
            hooks['response'] = list(hooks.get('response', [])) + [record_response]
            super().__init__(*a, **kw)
    httpx.Client = AuditedClient
    source = Path(__file__).resolve().parents[1] / 'data' / 'jobs-20261023.csv'
    if (output/'manifest.json').exists():
        attempt_count=len(list(output.glob('manifest-attempt-*.json')))+1
        (output/'manifest.json').rename(output/f'manifest-attempt-{attempt_count}.json')
    write(output/'manifest.json', {'started_at':datetime.now(timezone.utc).isoformat(),
        'csv_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'embedding_model':settings.embedding_model, 'embedding_dimensions':settings.embedding_dimensions,
        'rerank_model':settings.rerank_model, 'generation_model':settings.chat_model,
        'generation_timeout_seconds':settings.chat_timeout_seconds,
        'implementation_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('job_rag').rglob('*.py'))},
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'models_are_real':True, 'transport':'production_functions_and_real_https',
        'provider_secrets_logged':False})
    db = Database(settings)
    try:
        db.initialize()
        imported = import_csv(db, settings, source.read_bytes(), 'boss')
        write(output/'import.json', imported)
        print('Real embedding indexing started; completed tasks survive restart.',flush=True)
        indexed = run_index_tasks(db, settings)
        write(output/'index.json',indexed)
        if indexed['failed']:
            raise RuntimeError('Real embedding index failures; not accepted as completed')
        stats=knowledge_base_stats(db, settings)
        with db.session() as session:
            chunks=session.scalar(select(func.count()).select_from(Chunk))
            vectors=session.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding.is_not(None)))
        write(output/'stats.json',{**stats,'chunks':chunks,'vectors':vectors})
        assert stats['total']==stats['indexed']==593 and chunks==vectors and vectors>0
        questions=[
            ('overview','统计岗位职责或者任职要求出现RAG的岗位中，相关的技术要求是什么？请仅基于提供的岗位证据总结并引用，不推算全库总数或占比，保留必备、优先和二选一关系；unknown只表示未核验。'),
            ('retrieval','RAG知识库文档解析、切分、Embedding、向量数据库、混合检索、重排与检索效果评测有哪些具体岗位要求？只总结提供的来源，逐项引用，不能推算总体数量。'),
            ('engineering','RAG岗位对Agent、Python、后端API集成、部署、权限、监控和评测有哪些具体要求？只总结检索证据，引用来源，区分职责、必备、优先和任选关系，不能推广到所有岗位。')]
        results=[]
        for name, question in questions:
            path=output/f'{name}.json'
            # Preserve a completed response if resuming indexing or generation.
            if path.exists():
                result=json.loads(path.read_text())
                if result.get('mode')!='hybrid' or result.get('answer_mode')!='llm' or not result.get('rerank',{}).get('applied'):
                    attempt_count=len(list(output.glob(f'{name}-attempt-*.json')))+1
                    path.rename(output/f'{name}-attempt-{attempt_count}.json')
            if not path.exists():
                result=answer(db,settings,SearchRequest(query=question,limit=8,generate=True,rerank=True,infer_filters=False,include_closed=True))
                write(path,result)
            if result['mode']!='hybrid' or result['answer_mode']!='llm' or not result.get('rerank',{}).get('applied'):
                raise RuntimeError(f'{name}: a required real model stage fell back; inspect saved result')
            results.append({'name':name,'retrieval_mode':result['mode'],'answer_mode':result['answer_mode'],
                'rerank_applied':result['rerank']['applied'],'sources':len(result['results'])})
            print(name, 'real hybrid/rerank/generation PASS',flush=True)
        write(output/'completion.json',{'status':'PASS','completed_at':datetime.now(timezone.utc).isoformat(),
              'runs':results,'provider_calls_this_process':len(events),
              'operations_this_process':dict(Counter(e['operation'] for e in events)),
              'note':'Provider log may include earlier attempts if resumed; no model fallback accepted.'})
    finally:
        db.engine.dispose()
        httpx.Client=original_client


if __name__=='__main__':
    main()
