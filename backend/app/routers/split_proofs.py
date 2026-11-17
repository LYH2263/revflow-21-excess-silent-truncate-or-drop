from fastapi import APIRouter

from app.services import settle as svc

router = APIRouter(tags=["拆笔证明"])


@router.get("/settle-runs/{run_id}/split-proofs")
def get_split_proofs(run_id: int):
    """只读：按归并运行 id 查询本轮拆笔证明。"""
    return svc.list_split_proofs(run_id)
