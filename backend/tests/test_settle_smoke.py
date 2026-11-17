from pathlib import Path
import os
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DATA_DIR", str(ROOT / "backend" / "data_test"))
os.environ.setdefault("FIXTURES_DIR", str(ROOT / "fixtures"))

DATA_DIR = Path(os.environ["DATA_DIR"])
db_path = DATA_DIR / "app.db"
if db_path.exists():
    db_path.unlink()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.modules.excess_split import split_reversal  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["项目"] == "冲流台"


def test_split_reversal_pure():
    s = split_reversal(12000, 8000)
    assert (s.applied_cents, s.excess_cents) == (8000, 4000)
    assert s.status == "部分归并"
    assert s.split_kind == "部分配平"

    full = split_reversal(5000, 25000)
    assert (full.applied_cents, full.excess_cents) == (5000, 0)
    assert full.status == "已归并"

    none = split_reversal(3000, 0)
    assert (none.applied_cents, none.excess_cents) == (0, 3000)
    assert none.status == "已隔离"
    assert none.split_kind == "整笔超额"

    with pytest.raises(ValueError):
        split_reversal(-1, 100)


def test_settle_and_verify(client):
    d = client.get("/api/dashboard").json()
    assert d["账户数"] >= 3
    assert d["正向笔数"] >= 5
    assert d["冲正笔数"] >= 5

    run = client.post("/api/settle-runs")
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "完成"
    assert body["quarantine_count"] >= 2
    # 超额样本：冲 12000 打 8000 敞口 → 配平 8000，隔离 4000
    assert body["applied_reversal_cents"] == 10000 + 5000 + 18000 + 8000
    assert body["excess_quarantine_cents"] == 4000
    # 未冲完的敞口：FWD-002 剩 20000 + FWD-004 未冲 50000
    assert body["remaining_exposure_cents"] == 20000 + 50000

    q = client.get("/api/quarantine").json()
    assert any(x["reason"] == "冲正无原单" for x in q)
    excess = [x for x in q if x["reason"] == "冲正超额"]
    assert len(excess) == 1
    row = excess[0]
    assert row["entry_key"] == row["parent_entry_key"] == "REV-20261116-005"
    assert row["amount_cents"] == 4000
    assert row["split_applied_cents"] == 8000
    assert row["exposure_cents"] == 8000
    assert row["split_kind"] == "部分配平"

    revs = {e["entry_key"]: e for e in client.get("/api/entries?kind=冲正").json()}
    split = revs["REV-20261116-005"]
    assert split["status"] == "部分归并"
    assert split["applied_cents"] == 8000
    assert split["excess_cents"] == 4000
    assert split["amount_cents"] == 12000
    assert split["applied_cents"] + split["excess_cents"] == split["amount_cents"]

    report = client.post("/api/verify-reports")
    assert report.status_code == 200, report.text
    rj = report.json()
    assert rj["consistent"] == 1
    assert rj["ledger_net_cents"] == rj["balance_sum_cents"]
    detail = rj["detail"]
    assert detail["本轮已归并冲正额分"] == body["applied_reversal_cents"]
    assert detail["本轮超额隔离额分"] == body["excess_quarantine_cents"]
    assert detail["超额隔离分栏合计分"] == body["excess_quarantine_cents"]
    assert detail["剩余敞口分"] == body["remaining_exposure_cents"]
    assert detail["可溯源超额行数"] == detail["超额隔离行数"] == detail["超额分栏笔数"] == 1

    reports = client.get("/api/verify-reports").json()
    assert reports[0]["detail"]["本轮超额隔离额分"] == 4000


def test_persisted_after_reload(client):
    """刷新（重新读取）后拆分痕迹仍在：分栏、隔离行、归并报告三处一致。"""
    revs = {e["entry_key"]: e for e in client.get("/api/entries?kind=冲正").json()}
    split = revs["REV-20261116-005"]
    assert (split["applied_cents"], split["excess_cents"]) == (8000, 4000)

    q = [x for x in client.get("/api/quarantine").json() if x["reason"] == "冲正超额"]
    assert q and q[0]["parent_entry_key"] == "REV-20261116-005"

    run = client.get("/api/settle-runs").json()[0]
    assert run["excess_quarantine_cents"] == 4000

    # 重跑一轮（无待归并）不会抹掉既有拆分痕迹
    again = client.post("/api/settle-runs").json()
    assert again["status"] == "完成"
    revs = {e["entry_key"]: e for e in client.get("/api/entries?kind=冲正").json()}
    assert revs["REV-20261116-005"]["applied_cents"] == 8000
    assert revs["REV-20261116-005"]["excess_cents"] == 4000
    assert client.post("/api/verify-reports").json()["detail"]["剩余敞口分"] == 70000


def test_split_columns_immutable(client):
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE ledger_entries SET applied_cents = 1 WHERE entry_key = 'REV-20261116-005'"
            )
        conn.rollback()
        # 状态等其它列仍可更新
        conn.execute(
            "UPDATE ledger_entries SET note = note WHERE entry_key = 'REV-20261116-005'"
        )
        conn.rollback()
    finally:
        conn.close()


def test_fail_closed_rollback(client, monkeypatch):
    """落库中途失败 → 分栏、隔离行、余额全部回到操作前。"""
    from app.services import settle as svc

    before_run = client.get("/api/settle-runs").json()[0]
    before_q = len(client.get("/api/quarantine").json())
    before_bal = client.get("/api/dashboard").json()["余额合计分"]

    # 制造一笔新的超额冲正
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO ledger_entries(
          entry_key, account_id, kind, amount_cents, biz_ref, target_entry_key,
          booked_at, status, note
        ) VALUES ('REV-FAIL-001', 1, '冲正', 9000, 'ORD-9003', 'FWD-20261116-005',
                  '2026-11-16T19:00:00Z', '待归并', '')
        """
    )
    conn.commit()
    conn.close()

    original = svc._check_run_totals

    def boom(*args, **kwargs):
        raise RuntimeError("注入失败：落库后自校验失败")

    monkeypatch.setattr(svc, "_check_run_totals", boom)
    r = client.post("/api/settle-runs")
    assert r.status_code == 500
    assert "回滚" in r.json()["detail"]
    monkeypatch.setattr(svc, "_check_run_totals", original)

    after_run = client.get("/api/settle-runs").json()[0]
    assert after_run["id"] == before_run["id"]
    assert len(client.get("/api/quarantine").json()) == before_q
    assert client.get("/api/dashboard").json()["余额合计分"] == before_bal

    revs = {e["entry_key"]: e for e in client.get("/api/entries?kind=冲正").json()}
    assert revs["REV-FAIL-001"]["status"] == "待归并"
    assert revs["REV-FAIL-001"]["applied_cents"] is None
    assert revs["REV-FAIL-001"]["excess_cents"] is None

    # 恢复后重跑应正常：目标已无剩余敞口 → 整笔超额隔离
    run = client.post("/api/settle-runs").json()
    assert run["status"] == "完成"
    assert run["applied_reversal_cents"] == 0
    assert run["excess_quarantine_cents"] == 9000
    row = [
        x
        for x in client.get("/api/quarantine").json()
        if x["entry_key"] == "REV-FAIL-001"
    ][0]
    assert row["split_kind"] == "整笔超额"
    assert row["amount_cents"] == 9000
    assert row["split_applied_cents"] == 0
    assert row["exposure_cents"] == 0

    report = client.post("/api/verify-reports").json()
    assert report["consistent"] == 1


def test_split_invariant_rejects_silent_truncation():
    """拆笔等式必须成立：禁止把 excess 静默截成 0。"""
    from app.modules.excess_split import Split, assert_split_invariant

    silent = Split(amount_cents=12000, applied_cents=8000, excess_cents=0)
    with pytest.raises(ValueError):
        assert_split_invariant(silent, 12000)

    # 已按全额入账却把敞口损失记成 0：amount 与分栏对不上被拒
    over_applied = Split(amount_cents=12000, applied_cents=12000, excess_cents=4000)
    with pytest.raises(ValueError):
        assert_split_invariant(over_applied, 12000)

    ok = Split(amount_cents=12000, applied_cents=8000, excess_cents=4000)
    assert_split_invariant(ok, 12000)


def test_split_proof_endpoint(client):
    """新增拆笔证明实体：按归并运行 id 只读查询，字段与分栏/隔离行同源。"""
    runs = client.get("/api/settle-runs").json()
    if not runs:
        assert client.post("/api/settle-runs").status_code == 200
        runs = client.get("/api/settle-runs").json()
    # 模块内前面的用例可能又跑了一轮；取真正含该笔拆分证明的运行
    run_id = None
    for cand in runs:
        proofs = client.get(f"/api/settle-runs/{cand['id']}/split-proofs").json()
        if any(p["parent_entry_key"] == "REV-20261116-005" for p in proofs):
            run_id = cand["id"]
            break
    assert run_id is not None
    r = client.get(f"/api/settle-runs/{run_id}/split-proofs")
    assert r.status_code == 200, r.text
    proofs = {p["parent_entry_key"]: p for p in r.json()}

    proof = proofs["REV-20261116-005"]
    assert proof["settle_run_id"] == run_id
    assert proof["amount_cents"] == 12000
    assert proof["applied_cents"] == 8000
    assert proof["excess_cents"] == 4000
    assert proof["exposure_before_cents"] == 8000
    assert proof["split_kind"] == "部分配平"
    assert proof["balanced"] is True
    assert proof["quarantine_item_id"] is not None
    assert proof["quarantine_reason"] == "冲正超额"

    # 同源：证明分栏 == 冲正分栏；证明超额 == 隔离行金额
    revs = {e["entry_key"]: e for e in client.get("/api/entries?kind=冲正").json()}
    rev = revs["REV-20261116-005"]
    assert proof["applied_cents"] == rev["applied_cents"]
    assert proof["excess_cents"] == rev["excess_cents"]
    assert proof["amount_cents"] == rev["applied_cents"] + rev["excess_cents"]
    q = {x["id"]: x for x in client.get("/api/quarantine").json()}
    qrow = q[proof["quarantine_item_id"]]
    assert qrow["amount_cents"] == proof["excess_cents"]
    assert qrow["parent_entry_key"] == proof["parent_entry_key"]

    # 整笔隔离（无原单）也落证明，excess = 全款、applied = 0
    blocked = proofs["REV-20261116-004"]
    assert (blocked["applied_cents"], blocked["excess_cents"]) == (0, 12000)
    assert blocked["quarantine_item_id"] is not None


def test_split_proof_endpoint_unknown_run(client):
    assert client.get("/api/settle-runs/999999/split-proofs").status_code == 404


def test_split_proofs_immutable(client):
    """拆笔证明不可改不可删：审计凭证不能被报告文案替换。"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE split_proofs SET excess_cents = 0 WHERE parent_entry_key = 'REV-20261116-005'")
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM split_proofs WHERE parent_entry_key = 'REV-20261116-005'")
        conn.rollback()
    finally:
        conn.close()


def test_verify_report_carries_proof_source(client):
    """互证报告字段直接取自分栏/隔离行/拆笔证明，不得只改文案。"""
    report = client.post("/api/verify-reports").json()
    detail = report["detail"]
    assert report["consistent"] == 1
    assert detail["拆笔证明配平台计分"] == detail["本轮已归并冲正额分"]
    assert detail["拆笔证明超额合计分"] == detail["本轮超额隔离额分"]
    assert detail["拆笔证明等式不平衡笔数"] == 0
    latest_run_proofs = client.get(
        "/api/settle-runs/" + str(report["settle_run_id"]) + "/split-proofs"
    ).json()
    assert detail["证明挂隔离行笔数"] == sum(1 for p in latest_run_proofs if p["excess_cents"] > 0)
