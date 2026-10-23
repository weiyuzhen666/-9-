from typing import Annotated

import json
from pathlib import Path

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import text

import recommender.student  # triggers student Provider registration into PROVIDERS dict
from recommender.contracts import Algorithm, AlgorithmNotImplemented, RecommendationRequest, RecommendationResult, PROVIDERS, recommend
from recommender.data import ContractError
from .config import DATASET, SPLIT
from .errors import APIError
from .schemas import IdPath, Input, identifier
from .security import ActorDependency

router = APIRouter(tags=["学生算法预留边界"])


class RecommendationQuery(Input):
    limit: int = Field(default=10, ge=1, le=50)


class ExplanationQuery(Input):
    movie_id: str = Field(min_length=1, max_length=16)


def invoke(algorithm: Algorithm, kind: str, uid: int, limit: int):
    request = RecommendationRequest(kind, uid, limit, "business", DATASET, SPLIT)
    try:
        return recommend(algorithm, request)
    except AlgorithmNotImplemented:
        raise APIError(501, "ALGORITHM_NOT_IMPLEMENTED", "此推荐算法留给学生实现", {
            "status": "not_implemented", "algorithm": algorithm.value, "subject_key": kind + ":" + str(uid),
            "dataset_version": DATASET, "split_version": SPLIT, "runtime_mode": "business",
            "model_version": None, "batch_id": None, "items": []}) from None
    except ContractError as exc:
        raise APIError(503 if exc.code in {"MODEL_BINDING_INVALID", "DATA_IDENTITY_INVALID", "DATA_MODE_INVALID"} else 500,
            exc.code, str(exc)) from None


@router.get("/experiments/algorithms")
def algorithms():
    return {"items": [{"algorithm": algorithm.value, "status": "registered" if algorithm in PROVIDERS else "not_implemented"} for algorithm in Algorithm]}


@router.get("/experiments/evaluations")
def evaluations():
    """Serve the offline evaluation metrics produced by recommender/student/evaluate_all.py.

    The metrics file is generated on the host under models/evaluation/metrics.json
    and mirrored into the container-visible models/business/metrics.json (compose
    only bind-mounts models/business).
    """
    candidates = [
        Path("/app/models/business/metrics.json"),
        Path("models/business/metrics.json"),
        Path("models/business/metrics.json"),
    ]
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise APIError(500, "EVALUATION_READ_FAILED", f"评价文件解析失败: {exc}") from None
            return {
                "status": "ready",
                "metrics": data,
                "dataset_version": DATASET,
                "split_version": SPLIT,
                "source": str(path),
            }
    raise APIError(501, "EVALUATION_NOT_IMPLEMENTED", "评价流程留给学生实现；业务API不连接evaluation数据库", {
        "status": "not_implemented", "metrics": None, "dataset_version": DATASET, "split_version": SPLIT})


@router.get("/me/recommendations/{algorithm}", response_model=RecommendationResult)
def my_recommendations(algorithm: Algorithm, actor: ActorDependency, query: Annotated[RecommendationQuery, Query()]):
    return invoke(algorithm, "app", actor.account_id, query.limit)


@router.get("/demo/history-users/{ml_user_id}/recommendations/{algorithm}", response_model=RecommendationResult)
def history_recommendations(ml_user_id: IdPath, algorithm: Algorithm, request: Request,
                            query: Annotated[RecommendationQuery, Query()]):
    uid = identifier(ml_user_id)
    with request.app.state.db.connection() as conn:
        if conn.execute(text("SELECT ml_user_id FROM history_users WHERE ml_user_id=:id"), {"id": uid}).first() is None:
            raise APIError(404, "HISTORY_USER_NOT_FOUND", "历史匿名用户不存在")
    return invoke(algorithm, "ml", uid, query.limit)


def _movie_title(conn, movie_id: str) -> str:
    row = conn.execute(
        text("SELECT title_zh, movielens_title FROM movies WHERE movie_id=:m"),
        {"m": movie_id},
    ).first()
    if row is None:
        return movie_id
    return row[0] or row[1] or movie_id


def _llm_explain(evidence: dict) -> tuple[str, str]:
    """Ask the LLM to turn real evidence into plain Chinese. Returns (text, status).
    status: 'ok' | 'unavailable'. The prompt forbids inventing movies/ratings;
    when the LLM is unreachable we degrade to an evidence-only display."""
    from .assistant import _llm_config
    import urllib.request

    if not evidence.get("evidence_sufficient"):
        return (evidence.get("note") or "依据不足，无法生成个性化解释。"), "no_evidence"

    cfg = _llm_config()
    if not cfg["api_key"]:
        return "", "unavailable"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content":
                "你是电影推荐解释器。根据给定的真实推荐依据，用中文写2-3句自然的推荐理由，"
                "必须与依据一一对应（引用用户评过的电影、评分、类型匹配或相似度）。"
                "严禁增加任何电影、编造评分或更改推荐列表；依据不足时直接说明依据不足。"},
            {"role": "user", "content": "推荐依据JSON：\n" + json.dumps(evidence, ensure_ascii=False)},
        ],
        "temperature": 0.3,
    }
    try:
        req = urllib.request.Request(
            cfg["base_url"].rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text_out = (data["choices"][0]["message"].get("content") or "").strip()
        return (text_out, "ok") if text_out else ("", "unavailable")
    except Exception:
        return "", "unavailable"


@router.get("/demo/history-users/{ml_user_id}/recommendations/{algorithm}/explanation")
def explain_recommendation(ml_user_id: IdPath, algorithm: Algorithm, request: Request,
                           query: Annotated[ExplanationQuery, Query()]):
    """S4: real evidence for one recommended movie + LLM plain-language explanation."""
    uid = identifier(ml_user_id)
    with request.app.state.db.connection() as conn:
        if conn.execute(text("SELECT ml_user_id FROM history_users WHERE ml_user_id=:id"), {"id": uid}).first() is None:
            raise APIError(404, "HISTORY_USER_NOT_FOUND", "历史匿名用户不存在")

    from recommender.student.explain import explain_item
    req = RecommendationRequest("ml", uid, 10, "business", DATASET, SPLIT)
    evidence = explain_item(algorithm, req, query.movie_id)

    with request.app.state.db.connection() as conn:
        evidence["movie_title"] = _movie_title(conn, evidence["movie_id"])
        rated_titles = {}
        for item in evidence["based_on"]:
            rated_titles[item["rated_movie_id"]] = _movie_title(conn, item["rated_movie_id"])
    evidence["rated_titles"] = rated_titles

    explanation, llm_status = _llm_explain(evidence)
    return {
        "user": evidence["user"],
        "algorithm": evidence["algorithm"],
        "movie_id": evidence["movie_id"],
        "movie_title": evidence["movie_title"],
        "based_on": evidence["based_on"],
        "rated_titles": evidence["rated_titles"],
        "evidence_sufficient": evidence["evidence_sufficient"],
        "note": evidence.get("note", ""),
        "explanation": explanation,
        "llm_status": llm_status,
    }
