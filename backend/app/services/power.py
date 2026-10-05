"""供电系统业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import threading
from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "power"
REQUIRED_FIELDS = ["设备编号", "设备类型", "电压等级"]
STATUS_ORDER = ["正常", "负荷过高", "绝缘降低", "已修复"]
ACTION_RULES = {"负荷预警": "负荷过高", "绝缘报警": "绝缘降低", "安排修复": "已修复"}
NEGATIVE_ACTIONS = ["负荷预警", "绝缘报警"]
REPAIR_ACTION = "安排修复"
REPAIR_REQUIRED_FIELDS = ["运行负荷", "绝缘电阻"]
REPORT_FIELDS = ["设备编号", "设备类型", "电压等级", "所属区域", "运行负荷", "绝缘电阻", "上次试验", "设备状态"]
UNBACKFILLED_MARK = "上次试验日期缺失或无法识别，未能回填到月度报表"

# 动作是「读-改-写」一整串，必须串行化，否则并发的两次修复会都判定成首次生效。
ACTION_LOCK = threading.Lock()


def parse_test_month(value: Any) -> str | None:
    """把上次试验日期归一到「YYYY-MM」；认不出来的返回 None，由报表标注。"""
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(normalized, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    return None


class PowerService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["设备状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """执行动作并落库，返回 (设备, 回执说明, 是否生效)。

        安排修复必须把本次录入的运行负荷、绝缘电阻一起落库，回执与列表读的
        都是这份落库结果；设备已修复时重复提交不再生效，避免并发双击把
        最后一次读数覆盖掉。
        """
        with ACTION_LOCK:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"供电设备 {entry_id} 不存在或已归档", False
            if action not in ACTION_RULES:
                return None, f"动作「{action}」不属于供电系统可执行范围", False
            target = ACTION_RULES[action]
            if target not in STATUS_ORDER:
                return None, f"目标状态「{target}」不在允许的状态序列里", False
            if action == REPAIR_ACTION:
                if entry.get("status") == "已修复":
                    return entry, f"供电设备 {entry_id} 已完成修复，重复提交未生效", False
                missing = [field for field in REPAIR_REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
                if missing:
                    return None, f"安排修复需要随动作录入本次读数：{'、'.join(missing)}", False
                test_date, error = self._resolve_test_date(values.get("上次试验"))
                if error:
                    return None, error, False
                # 读数只保留最新一版：直接覆盖，不留历史版本。
                entry["运行负荷"] = str(values["运行负荷"]).strip()
                entry["绝缘电阻"] = str(values["绝缘电阻"]).strip()
                entry["上次试验"] = test_date
            entry["status"] = target
            entry["设备状态"] = target
            entry["pending"] = target != STATUS_ORDER[-1]
            entry["abnormal"] = action in NEGATIVE_ACTIONS
            return entry, f"供电设备已{action}", True

    def monthly_report(self, month: str | None = None) -> tuple[dict[str, Any] | None, str]:
        """月度试验报表：读数取当前落库的最新一版，与列表、详情同源。

        存量记录按上次试验日期回填到对应月份；日期缺失或认不出来的
        归到 unbackfilled 并逐条标注，不静默丢弃。
        """
        target = (month or "").strip() or date.today().strftime("%Y-%m")
        try:
            datetime.strptime(target, "%Y-%m")
        except ValueError:
            return None, f"报表月份「{target}」格式应为 YYYY-MM"
        items: list[dict[str, Any]] = []
        unbackfilled: list[dict[str, Any]] = []
        for row in store.rows(MODULE):
            record = {field: row.get(field) for field in REPORT_FIELDS}
            record["id"] = row.get("id")
            record["设备状态"] = row.get("status")
            test_month = parse_test_month(row.get("上次试验"))
            if test_month is None:
                unbackfilled.append({**record, "标注": UNBACKFILLED_MARK})
            elif test_month == target:
                items.append(record)
        return {
            "module": MODULE,
            "month": target,
            "generated_at": date.today().isoformat(),
            "items": items,
            "total": len(items),
            "unbackfilled": unbackfilled,
            "unbackfilled_total": len(unbackfilled),
        }, ""

    def _resolve_test_date(self, value: Any) -> tuple[str, str]:
        """修复落库的试验日期：没填取当天，填了必须是合法日期。"""
        text = str(value or "").strip()
        if not text:
            return date.today().isoformat(), ""
        if parse_test_month(text) is None:
            return "", f"上次试验日期「{text}」无法识别，请按 YYYY-MM-DD 填写"
        normalized = text.replace("/", "-").replace(".", "-")
        try:
            return datetime.strptime(normalized, "%Y-%m-%d").date().isoformat(), ""
        except ValueError:
            return "", f"上次试验日期「{text}」无法识别，请按 YYYY-MM-DD 填写"
