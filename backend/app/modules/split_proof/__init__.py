"""拆笔证明：一次冲正拆成「配平前缀」与「超额隔离」的不可变凭证。

每条证明挂在一个归并运行下，键为原冲正键，记录：

- ``parent_entry_key``：原冲正键（与冲正流水、隔离行共享）；
- ``applied_cents`` / ``excess_cents``：不可变分栏；
- ``exposure_before_cents``：配平前目标正向剩余敞口；
- ``amount_cents``：原冲正额，恒满足 applied + excess = amount。

证明是只读审计实体，不参与余额派生；余额只认 ``ledger_entries.applied_cents``。
拆分类别常量统一在 ``app.modules.excess_split``，证明与隔离行同源使用同一取值。
"""
from __future__ import annotations

from app.modules.excess_split import (
    EXPOSURE_SPLIT_KINDS,
    SPLIT_KIND_BLOCKED,
    SPLIT_KINDS,
)

__all__ = ["EXPOSURE_SPLIT_KINDS", "SPLIT_KIND_BLOCKED", "SPLIT_KINDS"]
