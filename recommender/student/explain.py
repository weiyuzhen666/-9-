"""S4: extract the real evidence behind a single recommendation item.

For a given (algorithm, user, recommended movie) triple, reconstruct exactly
which of the user's ratings and which similarity values participated in the
recommendation score -- using the SAME provider artifacts and the SAME scoring
code paths as recommend(), so the evidence can never drift from the ranking.
"""
from recommender.contracts import Algorithm, RecommendationRequest


def _business_user_items(request: RecommendationRequest) -> dict[str, float]:
    """Same history source as ContentProvider/ItemCFProvider.recommend()."""
    if request.runtime_mode == "business":
        from recommender.business import read_history
        history = read_history(request)
        return {fb.movie_id: float(fb.rating) for fb in history.ratings}
    from .common import eval_user_ratings
    return eval_user_ratings(str(request.subject_id))


def explain_item(algorithm: Algorithm, request: RecommendationRequest, movie_id: str) -> dict:
    import recommender.student  # noqa: F401  (register providers)
    from recommender.contracts import PROVIDERS

    provider = PROVIDERS.get(algorithm)
    if provider is None:
        return {"user": f"ml:{request.subject_id}", "algorithm": algorithm.value,
                "movie_id": str(movie_id), "based_on": [], "evidence_sufficient": False,
                "note": "算法未注册"}

    target = str(movie_id)
    user_items = _business_user_items(request)
    based_on: list[dict] = []

    if not user_items:
        return {"user": f"ml:{request.subject_id}", "algorithm": algorithm.value,
                "movie_id": target, "based_on": [], "evidence_sufficient": False,
                "note": "该用户无历史评分，推荐来自热门兜底策略，无个性化依据"}

    if algorithm is Algorithm.content:
        # Content scoring: score(X) = sum over user items m of sim(m,X)*weight(rating(m)),
        # where X must appear in neighbors[m] (top-K content neighbours) and
        # weight(r) = max(0.1, (r-2.5)/2.5). Re-derive each contributing term.
        movie_genres = provider.movie_genres
        target_genres = movie_genres.get(target, set())
        for mid, rating in user_items.items():
            hit = next((sim for m, sim in provider.neighbors.get(mid, []) if m == target), None)
            if hit is None:
                continue
            weight = max(0.1, (rating - 2.5) / 2.5)
            based_on.append({
                "rated_movie_id": mid,
                "rating": rating,
                "similarity": round(hit, 4),
                "weight": round(weight, 4),
                "contribution": round(hit * weight, 4),
                "common_genres": sorted(movie_genres.get(mid, set()) & target_genres),
            })
        based_on.sort(key=lambda d: -d["contribution"])

    elif algorithm is Algorithm.itemcf:
        # ItemCF scoring: score(X) = sum(sim*centered)/sum(|sim|) + item_mean(X),
        # centered = rating - item_mean(rated movie). Re-derive each term.
        for mid, rating in user_items.items():
            hit = next((sim for m, sim in provider.neighbors.get(mid, []) if m == target), None)
            if hit is None:
                continue
            centered = rating - provider.item_mean.get(mid, 3.5)
            based_on.append({
                "rated_movie_id": mid,
                "rating": rating,
                "similarity": round(hit, 4),
                "centered_rating": round(centered, 4),
                "contribution": round(hit * centered, 4),
            })
        based_on.sort(key=lambda d: -abs(d["contribution"]))

    else:
        return {"user": f"ml:{request.subject_id}", "algorithm": algorithm.value,
                "movie_id": target, "based_on": [], "evidence_sufficient": False,
                "note": "该算法的推荐依据暂不支持逐条解释"}

    note = "" if based_on else "目标电影不在用户已评分电影的内容/协同邻居中，依据不足"
    return {
        "user": f"ml:{request.subject_id}",
        "algorithm": algorithm.value,
        "movie_id": target,
        "based_on": based_on[:8],
        "evidence_sufficient": bool(based_on),
        "note": note,
    }
