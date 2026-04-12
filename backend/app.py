"""FastAPI application — routes, REST API, and background task queue."""
import asyncio
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func

from backend.database import setup_database, get_db
from backend.models import Run, Document, Classification, Entity, ReviewItemDB
from backend.pipeline.processor import run_url_scrape, run_source_scrape
from backend.csv_export import build_run_findings_csv

# Initialize app
app = FastAPI(title="Evil AI Scraper v2 API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ai-for-evil.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Queue worker
scrape_queue = asyncio.Queue()

async def queue_worker():
    """Worker to serialize scraping tasks and prevent Ollama/local overload."""
    while True:
        job = await scrape_queue.get()
        try:
            run_type = job["type"]
            run_id = job["run_id"]
            if run_type == "url":
                await run_url_scrape(run_id, job["url"])
            elif run_type == "source":
                await run_source_scrape(
                    run_id, 
                    job["sources"], 
                    job["max_results"], 
                    manifest_fresh=job.get("manifest_fresh", False)
                )
        except Exception as e:
            print(f"[Worker] Task failed: {e}")
        finally:
            scrape_queue.task_done()

@app.on_event("startup")
async def startup():
    setup_database()
    asyncio.create_task(queue_worker())

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/scrape/url")
async def api_scrape_url(request: Request):
    """Enqueue a URL scrape run."""
    data = await request.json()
    url = data.get("url", "").strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)
    user_id = data.get("user_id", "").strip()
    user_name = data.get("user_name", "").strip()

    with get_db() as db:
        run = Run(
            run_type="url",
            input_url=url,
            status="pending",
            user_id=user_id or None,
            user_name=user_name or None,
        )
        db.add(run)
        db.commit()
        run_id = run.id

    await scrape_queue.put({"type": "url", "run_id": run_id, "url": url})
    return JSONResponse({"run_id": run_id, "status": "pending"})


@app.post("/api/scrape/sources")
async def api_scrape_sources(request: Request):
    """Enqueue a source-based scrape run."""
    data = await request.json()
    sources = data.get("sources", [])
    if not sources:
        return JSONResponse({"error": "At least one source is required"}, status_code=400)

    allowed = {"arxiv", "github", "huggingface", "newsapi", "eu_ai_act", "patents", "manifest"}
    valid_sources = [s for s in sources if s in allowed or s.startswith("manifest:")]
    if not valid_sources:
        return JSONResponse({"error": "No valid sources selected"}, status_code=400)

    user_id = data.get("user_id", "").strip()
    user_name = data.get("user_name", "").strip()
    max_results = data.get("max_results", 60)
    manifest_fresh = bool(data.get("manifest_fresh", False))

    with get_db() as db:
        run = Run(
            run_type="source",
            status="pending",
            user_id=user_id or None,
            user_name=user_name or None,
        )
        run.sources_list = valid_sources
        db.add(run)
        db.commit()
        run_id = run.id

    await scrape_queue.put({
        "type": "source",
        "run_id": run_id,
        "sources": valid_sources,
        "max_results": max_results,
        "manifest_fresh": manifest_fresh
    })
    return JSONResponse({"run_id": run_id, "status": "pending"})


@app.get("/api/runs")
async def api_get_runs():
    """Get all runs."""
    with get_db() as db:
        runs = db.query(Run).order_by(Run.created_at.desc()).limit(50).all()
        return JSONResponse([{
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status,
            "run_type": r.run_type,
            "input_url": r.input_url,
            "sources": r.sources_list,
            "total_documents": r.total_documents,
            "evil_found": r.evil_found,
            "confirmed_count": r.confirmed_count,
            "contested_count": r.contested_count,
            "rejected_count": r.rejected_count,
            "avg_confidence": r.avg_confidence,
            "user_id": r.user_id,
            "user_name": r.user_name,
        } for r in runs])


@app.get("/api/run/{run_id}")
async def api_get_run(run_id: int):
    """Get a single run status and its queue position if pending."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JSONResponse({"error": "Run not found"}, status_code=404)
        
        queue_position = 0
        if run.status == "pending":
            queue_position = db.query(Run).filter(Run.status == "pending", Run.id < run.id).count() + 1
        
        return JSONResponse({
            "id": run.id,
            "status": run.status,
            "queue_position": queue_position,
            "total_documents": run.total_documents,
            "evil_found": run.evil_found,
            "confirmed_count": run.confirmed_count,
            "contested_count": run.contested_count,
            "rejected_count": run.rejected_count,
            "avg_confidence": run.avg_confidence,
            "error_message": run.error_message,
        })

@app.get("/api/run/{run_id}/documents")
async def api_get_documents(run_id: int):
    """Get the documents and classifications to power the dashboard table."""
    with get_db() as db:
        documents = db.query(Document).filter(Document.run_id == run_id).all()
        docs_data = []
        for doc in documents:
            classifications = db.query(Classification).filter(
                Classification.document_id == doc.id,
                Classification.matched == True,
            ).all()

            cls_data = []
            for c in classifications:
                cls_data.append({
                    "category_id": c.category_id,
                    "category_name": c.category_name,
                    "confidence": c.confidence,
                    "status": c.status,
                    "reasoning": c.reasoning,
                    "ai_system_name": c.ai_system_name,
                    "developer_org": c.developer_org,
                })

            max_conf = max((c.confidence for c in classifications), default=-1.0)

            docs_data.append({
                "id": doc.id,
                "url": doc.url,
                "title": doc.title,
                "source_name": doc.source_name,
                "document_type": doc.document_type,
                "keyword_matched": doc.keyword_matched,
                "classifications": cls_data,
                "max_confidence": max_conf,
            })
        
        docs_data.sort(key=lambda d: d["max_confidence"], reverse=True)
        return JSONResponse(docs_data)


@app.get("/api/run/{run_id}/export.csv")
async def api_export_run_csv(run_id: int):
    """Download matched classifications for this run as CSV (CLI-style entity/review columns)."""
    try:
        data, filename = build_run_findings_csv(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.get("/api/run/{run_id}/entities")
async def api_get_entities(run_id: int):
    """Get deduplicated entities for a run."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JSONResponse({"error": "Run not found"}, status_code=404)
        entities = db.query(Entity).filter(Entity.run_id == run_id).order_by(Entity.confidence.desc()).all()
        return JSONResponse([{
            "entity_id": e.entity_id,
            "entity_name": e.entity_name,
            "aliases": json.loads(e.aliases) if e.aliases else [],
            "canonical_code": e.canonical_code,
            "subgroup_name": e.subgroup_name,
            "confidence": e.confidence,
            "rationale": e.rationale,
            "source_urls": json.loads(e.source_urls) if e.source_urls else [],
            "review_status": e.review_status,
            "merge_confidence": e.merge_confidence,
            "seed_overlap": e.seed_overlap,
        } for e in entities])


@app.get("/api/run/{run_id}/review-queue")
async def api_get_review_queue(run_id: int):
    """Get review queue items for a run."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JSONResponse({"error": "Run not found"}, status_code=404)
        reviews = db.query(ReviewItemDB).filter(ReviewItemDB.run_id == run_id).all()
        return JSONResponse([{
            "review_id": r.review_id,
            "reason": r.reason,
            "severity": r.severity,
            "entity_name": r.entity_name,
            "source_url": r.source_url,
            "details": r.details,
            "suggested_code": r.suggested_code,
        } for r in reviews])


@app.post("/api/run/{run_id}/cancel")
async def api_cancel_run(run_id: int):
    """Mark a run as cancelled."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JSONResponse({"error": "Run not found"}, status_code=404)
        if run.status == "running":
            run.status = "cancelled"
            run.error_message = "Terminated by user."
            db.commit()
            return JSONResponse({"status": "cancelled", "message": "Run termination requested."})
        elif run.status == "pending":
            run.status = "cancelled"
            run.error_message = "Cancelled before starting."
            db.commit()
            return JSONResponse({"status": "cancelled", "message": "Run cancelled from queue."})
        return JSONResponse({"status": run.status, "message": "Run cannot be cancelled in its current state."})


@app.get("/api/leaderboard")
async def api_get_leaderboard():
    """Return the total unique AI systems found (case-insensitive distinct names) grouped by user_id."""
    from sqlalchemy import case, distinct, String
    with get_db() as db:
        system_expr = case(
            (Classification.ai_system_name == None, func.cast(Classification.document_id, String)),
            (Classification.ai_system_name == "", func.cast(Classification.document_id, String)),
            else_=func.lower(func.trim(Classification.ai_system_name))
        )
        
        results = db.query(
            Run.user_id,
            func.max(Run.user_name).label('user_name'),
            func.count(distinct(system_expr)).label('total_evil_found')
        ).join(
            Document, Document.run_id == Run.id
        ).join(
            Classification, Classification.document_id == Document.id
        ).filter(
            Run.status == "completed",
            Run.user_id.isnot(None), 
            Run.user_id != "",
            Classification.matched == True
        ).group_by(Run.user_id).order_by(
            func.count(distinct(system_expr)).desc()
        ).all()

        return JSONResponse([{
            "user_id": r.user_id,
            "user_name": r.user_name,
            "total_evil_found": r.total_evil_found,
        } for r in results])
