# 07-revflow（冲流台）

冲流台 — 正向与冲正流水净额归并：正向装载 → 冲正关联入账 → 净额归并落余额 → 未平/超额隔离 → 流水净额与余额互证。

**不是** 多源 Feed 归并，**不是** 作业依赖编排，**不是** CDC 变更流，**不是** 质检签发，**不是** 数仓分层建设，**不是** 交班过户。  
**也不是** 收银/退款 CRUD 后台、电商订单、报表 CSV 看板——主链是**流水管道与净额状态**，不是业务单据编辑台。

## 启动

```bash
# 后端
cd backend
pip install -r requirements.txt
set DATA_DIR=%CD%\data
set FIXTURES_DIR=%CD%\..\fixtures
uvicorn app.main:app --host 127.0.0.1 --port 10700

# 前端
cd frontend
npm install
npm run dev
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://127.0.0.1:5700 |
| 接口 | http://127.0.0.1:10700 |

## 主链

账户登记 → 装载正向流水 → 装载冲正并关联原单 → 跑净额归并（已配平落余额，未平/超额进隔离）→ 互证报告核对「流水净额 vs 账户余额」

## 超额冲正拆分

当冲正金额大于目标正向剩余敞口且敞口 > 0 时，不是整笔丢隔离，也不是静默截断：

- 不超过敞口的部分配平，计入账户余额与已归并冲正额；
- 超出敞口的部分作为「超额隔离」保留，可查可追溯；
- 两者共享原冲正键：冲正行写不可变分栏 `applied_cents` / `excess_cents`，同时落 `quarantine_items` 行（`parent_entry_key` = 原冲正键，并记录 `split_applied_cents`、`exposure_cents`、`split_kind`）；
- 冲正状态：全额配平 `已归并`、部分配平 `部分归并`、无可配平 `已隔离`；
- 一轮归并是单事务（`BEGIN IMMEDIATE`）：分栏、余额、隔离行、拆笔证明要么一起成功，要么全部回到操作前；落库后自校验失败即整轮回滚；
- 归并报告与互证报告的「已归并冲正额 / 超额隔离额 / 剩余敞口」直接取自分栏、隔离表、拆笔证明与流水派生余额，四方必须一致。

**拆笔路径（本仓择一）：** 按**配平前敞口**一次性切分 `applied` / `excess`；余额只认 `applied`，`excess` 必须同事务落隔离行，并满足 `applied + excess = 原冲正额`。禁止「已扣全额只改隔离态」。

**拆笔证明实体 `split_proofs`**（基线所无）：每条证明挂归并运行 id，记录原冲正键 `parent_entry_key`、`applied_cents`、`excess_cents`、配平前敞口 `exposure_before_cents`、`amount_cents`、`split_kind` 与所挂隔离行 `quarantine_item_id`；表级 CHECK 守住 `applied + excess = amount`，触发器守不可改不可删。只读查询接口：

```bash
GET /api/settle-runs/{run_id}/split-proofs
```

冲正流水、未平隔离、归并台与净额互证界面均展示分栏 / 证明字段，且全部来自同一份分栏与证明实体（同源派生，不靠改文案）。


## 界面约定

页面文案全部中文；入口：总览 / 账户 / 正向流水 / 冲正流水 / 归并台 / 未平隔离 / 净额互证。  
视觉：**左轨编号导航 + 右侧账册横线工作面**（Literata / JetBrains Mono，靛蓝强调）；**不是**交班台那种顶栏品牌+横向流程条。

## 与已有仓差异

| 仓 | 骨架 |
| --- | --- |
| Feedstitch | 多源解析→冲突隔离→水位 |
| Batchgate | 作业依赖→重试→水位 |
| Changeflow | 事件序→缺口→Sink 游标 |
| Checklane | 入检→规则→隔离签发 |
| Tiercraft | 贴源→明细→汇总→层间对账 |
| Shiftboard | 班次归属→交班互斥→批次过户 |
| **本仓** | **正向装载→冲正关联→净额归并→未平隔离→净额互证** |
