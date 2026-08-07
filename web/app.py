import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from agent.profile import ProfileExtractor
from agent.retriever import Retriever
from agent.reporter import ReportGenerator
from agent.matcher import Matcher
from agent.grad_retriever import GradProgramRetriever

app = FastAPI(title="途策必达留学 — 智能选校 Agent")

profile_extractor = ProfileExtractor()
retriever = Retriever()
report_generator = ReportGenerator()
matcher = Matcher()
grad_retriever = GradProgramRetriever()


class ProfileRequest(BaseModel):
    text: str


@app.post("/api/profile")
async def extract_profile(req: ProfileRequest):
    profile = profile_extractor.extract(req.text)
    return {"profile": profile}


class SearchRequest(BaseModel):
    profile: dict
    top_k: int = 15
    filters: Optional[dict] = None
    apply_fusion: bool = True


class SchoolSearchRequest(BaseModel):
    query: str
    top_k: int = 10


@app.post("/api/search")
async def search_cases(req: SearchRequest):
    result = retriever.search_similar_cases(
        profile=req.profile,
        top_k=req.top_k,
        filters=req.filters,
        apply_fusion=req.apply_fusion,
    )
    return result


@app.post("/api/schools/search")
async def search_schools(req: SchoolSearchRequest):
    result = retriever.search_schools(req.query, top_k=req.top_k)
    return result


@app.get("/api/search-by-metadata")
async def search_by_metadata(
    curriculum: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    school: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    result = retriever.search_by_metadata(
        curriculum=curriculum,
        doc_type=doc_type,
        school=school,
        limit=limit,
    )
    return result


class MatchRequest(BaseModel):
    profile: dict
    top_k: int = 15
    filters: Optional[dict] = None


class ClassifyRequest(BaseModel):
    profile: dict
    top_k: int = 15
    filters: Optional[dict] = None


@app.post("/api/matcher/classify")
async def classify_schools(req: ClassifyRequest):
    """对学校进行 冲刺/匹配/保底 三级分级。"""
    search_result = retriever.search_similar_cases(
        profile=req.profile,
        top_k=req.top_k,
        filters=req.filters,
        apply_fusion=True,
    )
    result = matcher.classify(req.profile, search_result)
    return result


@app.post("/api/match")
async def match_schools(req: MatchRequest):
    search_result = retriever.search_similar_cases(
        profile=req.profile,
        top_k=req.top_k,
        filters=req.filters,
        apply_fusion=True,
    )
    # 三级分级
    classify_result = matcher.classify(req.profile, search_result)
    # 生成报告时传入分级数据
    report = report_generator.generate(
        profile=req.profile,
        search_result=search_result,
        classify_result=classify_result,
        stream=False,
    )
    return {
        "report": report,
        "search_summary": {
            "total_hits": search_result["total_hits"],
            "by_doc_type": search_result["by_doc_type"],
            "query": search_result["query"],
        },
        "classification": classify_result,
    }


@app.post("/api/match/stream")
async def match_schools_stream(req: MatchRequest):
    search_result = retriever.search_similar_cases(
        profile=req.profile,
        top_k=req.top_k,
        filters=req.filters,
        apply_fusion=True,
    )
    classify_result = matcher.classify(req.profile, search_result)

    def sse_generator():
        # 先发送分级数据
        yield f"data: {json.dumps({'classification': classify_result})}\n\n"
        for event in report_generator.generate_stream_sse(
            req.profile, search_result, classify_result=classify_result,
        ):
            yield event

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 研究生项目 API ──────────────────────────────────────────


class GradSearchRequest(BaseModel):
    query: str
    top_k: int = 15
    country: Optional[str] = None
    school: Optional[str] = None
    degree: Optional[str] = None
    major_direction: Optional[str] = None
    field: Optional[str] = None


class GradCompareRequest(BaseModel):
    programs: list[dict]


@app.post("/api/grad/search")
async def grad_search(req: GradSearchRequest):
    result = grad_retriever.search_programs(
        query=req.query,
        top_k=req.top_k,
        country=req.country,
        school=req.school,
        degree=req.degree,
        major_direction=req.major_direction,
        field=req.field,
    )
    return result


@app.get("/api/grad/schools")
async def grad_schools():
    return grad_retriever.list_schools()


@app.get("/api/grad/filters")
async def grad_filters():
    return grad_retriever.list_filter_options()


@app.get("/api/grad/programs/{school}")
async def grad_programs_by_school(school: str):
    result = grad_retriever.search_by_school(school)
    return result


@app.get("/api/grad/program")
async def grad_program_detail(
    school: str = Query(...),
    program: str = Query(..., description="program_name"),
):
    detail = grad_retriever.get_program_detail(school, program)
    if detail is None:
        return {"error": "program not found", "school": school, "program_name": program}
    return detail


@app.post("/api/grad/compare")
async def grad_compare(req: GradCompareRequest):
    return grad_retriever.compare_programs(req.programs)


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
