"""FastAPI application — routes, templates, and background task runner."""
import asyncio
import json
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from backend.database import setup_database, get_db
from backend.models import Run, Document, Classification
from backend.pipeline.processor import run_url_scrape, run_source_scrape

# Paths
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

# Initialize app
app = FastAPI(title="Evil AI Scraper v2", version="2.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.on_event("startup")
async def startup():
    setup_database()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page — run logs, URL input, source selection."""
    with get_db() as db:
        runs = db.query(Run).order_by(Run.created_at.desc()).limit(50).all()
        runs_data = []
        for r in runs:
            runs_data.append({
                "id": r.id,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
                "finished_at": r.finished_at.strftime("%Y-%m-%d %H:%M") if r.finished_at else "",
                "status": r.status,
                "run_type": r.run_type,
                "input_url": r.input_url or "",
                "sources": r.sources_list,
                "total_documents": r.total_documents,
                "evil_found": r.evil_found,
                "confirmed_count": r.confirmed_count,
                "contested_count": r.contested_count,
                "rejected_count": r.rejected_count,
                "avg_confidence": r.avg_confidence,
                "error_message": r.error_message or "",
            })
    return templates.TemplateResponse("index.html", {
        "request": request,
        "runs": runs_data,
    })


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: int):
    """Detail dashboard for a single run."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return HTMLResponse("<h1>Run not found</h1>", status_code=404)

        run_data = {
            "id": run.id,
            "created_at": run.created_at.strftime("%Y-%m-%d %H:%M:%S") if run.created_at else "",
            "finished_at": run.finished_at.strftime("%Y-%m-%d %H:%M:%S") if run.finished_at else "",
            "status": run.status,
            "run_type": run.run_type,
            "input_url": run.input_url or "",
            "sources": run.sources_list,
            "total_documents": run.total_documents,
            "evil_found": run.evil_found,
            "confirmed_count": run.confirmed_count,
            "contested_count": run.contested_count,
            "rejected_count": run.rejected_count,
            "avg_confidence": run.avg_confidence,
            "error_message": run.error_message or "",
            "reviewer_name": run.reviewer_name or "",
        }

        # Get documents and classifications
        documents = db.query(Document).filter(Document.run_id == run_id).all()
        docs_data = []
        for doc in documents:
            classifications = db.query(Classification).filter(
                Classification.document_id == doc.id,
                Classification.matched == True,
            ).all()

            cls_data = []
            for c in classifications:
                criteria = {}
                try:
                    criteria = json.loads(c.criteria_scores) if c.criteria_scores else {}
                except json.JSONDecodeError:
                    pass
                cls_data.append({
                    "category_id": c.category_id,
                    "category_name": c.category_name,
                    "confidence": c.confidence,
                    "status": c.status,
                    "reasoning": c.reasoning,
                    "criteria_scores": criteria,
                    "ai_system_name": c.ai_system_name,
                    "developer_org": c.developer_org,
                    "abuse_description": c.abuse_description,
                    "is_gray_area": c.is_gray_area,
                    "criminal_or_controversial": c.criminal_or_controversial or "",
                    "descriptive_category": c.descriptive_category or "",
                    "tool_website_url": c.tool_website_url or "",
                    "public_tagline": c.public_tagline or "",
                    "stated_use_case": c.stated_use_case or "",
                    "target_victim": c.target_victim or "",
                    "primary_output": c.primary_output or "",
                    "harm_category": c.harm_category or "",
                    "gate_1": c.gate_1 or "",
                    "gate_2": c.gate_2 or "",
                    "gate_3": c.gate_3 or "",
                    "exclusion_1": c.exclusion_1 or "",
                    "exclusion_2": c.exclusion_2 or "",
                    "exclusion_3": c.exclusion_3 or "",
                    "include_in_repo": c.include_in_repo or "",
                    "evidence_summary": c.evidence_summary or "",
                })

            cls_data.sort(key=lambda c: c["confidence"], reverse=True)

            parts = [doc.title, doc.url, doc.source_name or ""]
            for c in cls_data:
                parts.extend([
                    c["category_id"], c["category_name"], c["status"],
                    c.get("ai_system_name") or "", c.get("developer_org") or "",
                    c.get("abuse_description") or "", c.get("reasoning") or "",
                    c.get("descriptive_category") or "", c.get("criminal_or_controversial") or "",
                    c.get("harm_category") or "", c.get("evidence_summary") or "",
                ])
            search_blob = " ".join(p for p in parts if p).lower()

            max_conf = max((c["confidence"] for c in cls_data), default=-1.0)
            status_tags = sorted({c["status"] for c in cls_data})

            docs_data.append({
                "id": doc.id,
                "url": doc.url,
                "title": doc.title,
                "source_name": doc.source_name,
                "document_type": doc.document_type,
                "keyword_matched": doc.keyword_matched,
                "classifications": cls_data,
                "search_blob": search_blob,
                "max_confidence": max_conf,
                "status_tags": status_tags,
            })

        docs_data.sort(
            key=lambda d: max((c["confidence"] for c in d["classifications"]), default=-1.0),
            reverse=True,
        )
        unique_sources = sorted(
            {d["source_name"] for d in docs_data if d.get("source_name")},
        )
        unique_categories = sorted({
            c["descriptive_category"] for d in docs_data for c in d["classifications"]
            if c.get("descriptive_category")
        })
        unique_coc = sorted({
            c["criminal_or_controversial"] for d in docs_data for c in d["classifications"]
            if c.get("criminal_or_controversial")
        })

        # Aggregate metrics for charts
        category_counts = {}
        source_counts = {}
        status_counts = {"confirmed": 0, "contested": 0, "rejected": 0, "gray_area": 0, "pending_criteria": 0}
        top_threats = []

        for doc in docs_data:
            for cls in doc["classifications"]:
                cat = cls["category_id"]
                category_counts[cat] = category_counts.get(cat, 0) + 1
                if cls["status"] in status_counts:
                    status_counts[cls["status"]] += 1
                if cls["confidence"] >= 0.5:
                    top_threats.append({
                        "name": cls.get("ai_system_name") or doc["title"][:60],
                        "category": cls["category_name"],
                        "confidence": cls["confidence"],
                        "status": cls["status"],
                        "url": doc["url"],
                        "ai_system_name": cls.get("ai_system_name") or "",
                    })

            if doc["source_name"]:
                source_counts[doc["source_name"]] = source_counts.get(doc["source_name"], 0) + 1

        top_threats.sort(key=lambda x: x["confidence"], reverse=True)
        top_threats = top_threats[:10]

    return templates.TemplateResponse("run_detail.html", {
        "request": request,
        "run": run_data,
        "documents": docs_data,
        "unique_sources": unique_sources,
        "unique_categories": unique_categories,
        "unique_coc": unique_coc,
        "category_counts": category_counts,
        "source_counts": source_counts,
        "status_counts": status_counts,
        "top_threats": top_threats,
    })


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/scrape/url")
async def api_scrape_url(request: Request, background_tasks: BackgroundTasks):
    """Start a URL scrape run."""
    data = await request.json()
    url = data.get("url", "").strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    reviewer_name = data.get("reviewer_name", "").strip()

    with get_db() as db:
        run = Run(
            run_type="url",
            input_url=url,
            status="pending",
            reviewer_name=reviewer_name or None,
        )
        db.add(run)
        db.commit()
        run_id = run.id

    background_tasks.add_task(_run_url_async, run_id, url)
    return JSONResponse({"run_id": run_id, "status": "started"})


@app.post("/api/scrape/sources")
async def api_scrape_sources(request: Request, background_tasks: BackgroundTasks):
    """Start a source-based scrape run."""
    data = await request.json()
    sources = data.get("sources", [])
    if not sources:
        return JSONResponse({"error": "At least one source is required"}, status_code=400)

    valid_sources = [s for s in sources if s in {
        "arxiv", "github", "huggingface", "newsapi", "eu_ai_act", "patents"
    }]
    if not valid_sources:
        return JSONResponse({"error": "No valid sources selected"}, status_code=400)

    reviewer_name = data.get("reviewer_name", "").strip()

    with get_db() as db:
        run = Run(
            run_type="source",
            status="pending",
            reviewer_name=reviewer_name or None,
        )
        run.sources_list = valid_sources
        db.add(run)
        db.commit()
        run_id = run.id

    background_tasks.add_task(_run_sources_async, run_id, valid_sources)
    return JSONResponse({"run_id": run_id, "status": "started"})


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
        } for r in runs])


@app.get("/api/run/{run_id}")
async def api_get_run(run_id: int):
    """Get a single run status."""
    with get_db() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JSONResponse({"error": "Run not found"}, status_code=404)
        return JSONResponse({
            "id": run.id,
            "status": run.status,
            "total_documents": run.total_documents,
            "evil_found": run.evil_found,
            "confirmed_count": run.confirmed_count,
            "contested_count": run.contested_count,
            "rejected_count": run.rejected_count,
            "avg_confidence": run.avg_confidence,
            "error_message": run.error_message,
        })


# ---------------------------------------------------------------------------
# Background task wrappers
# ---------------------------------------------------------------------------

async def _run_url_async(run_id: int, url: str):
    await run_url_scrape(run_id, url)


async def _run_sources_async(run_id: int, sources: list[str]):
    await run_source_scrape(run_id, sources)
