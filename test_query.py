from backend.database import get_db
from backend.models import Run, Document, Classification
from sqlalchemy import func, case, distinct, String

def test_query():
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

        for r in results:
            print(f"User: {r.user_name} ({r.user_id}), Distinct Found: {r.total_evil_found}")

if __name__ == "__main__":
    test_query()
