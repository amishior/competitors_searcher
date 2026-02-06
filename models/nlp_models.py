from typing import Any, Dict, List
import numpy as np

def emb_call(text: str) -> List[float]:
    rs = np.random.RandomState(abs(hash(text)) % (2**32))
    v = rs.normal(size=(1024,)).astype("float32")
    return v.tolist()

def rerank_call(user_query: str, documents: List[str], model_name: str = "qwen3-rerank", top_k: int = 100) -> List[Dict[str, Any]]:
    out = []
    qlen = max(len(user_query), 1)
    for i, d in enumerate(documents):
        score = 1.0 - abs(len(d) - qlen) / max(len(d), qlen, 1)
        out.append({"index": i, "score": float(score)})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[: min(top_k, len(out))]
