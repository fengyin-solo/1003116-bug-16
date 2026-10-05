"""供电系统接口：维护供电设备，覆盖负荷预警、绝缘报警、安排修复、月度试验报表。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.power import ConflictError, PowerService

router = APIRouter(prefix="/api/power", tags=["供电系统"])

service = PowerService()

LIST_FIELDS = ["设备编号", "设备类型", "电压等级", "所属区域", "运行负荷", "绝缘电阻", "上次试验", "设备状态"]
STATUSES = ["正常", "负荷过高", "绝缘降低", "已修复"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设备编号检索"),
    status: str | None = Query(default=None, description="正常、负荷过高、绝缘降低、已修复"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设备编号与状态过滤供电系统列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/monthly-report")
def monthly_report(month: str | None = Query(default=None, description="月份 YYYY-MM，默认当月")) -> dict[str, Any]:
    """供电系统月度试验报表：读数直接取设备最新落库记录，旧记录按上次试验日期回填。"""
    try:
        return service.monthly_report(month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出供电系统清单：返回当前过滤条件下的全量数据，与列表同源。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "power", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条供电设备明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"供电设备 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条供电设备，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="供电设备已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条供电设备执行负荷预警、绝缘报警、安排修复。

    安排修复必须随回执带上本次录入的运行负荷、绝缘电阻与版本号；
    并发重复提交（版本号过期）返回 409，两次修复只生效一次。
    """
    action = str(payload.values.get("action") or "").strip()
    try:
        entry, message = service.run_action(entry_id, action, payload.values)
    except ConflictError as exc:
        # 不允许静默吞掉：明确告诉前端本次修复未生效，读数仍是已落库的那版
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
