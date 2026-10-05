"""供电系统业务规则：状态流转、字段校验、修复读数落库与月度试验报表。

读数口径（列表 / 详情 / 运营概览必须同一份数据）：
- 存量记录沿用 seed 里的原始读数（可能是占位文本），报表里标注为「存量记录」；
- 安排修复时录入的运行负荷、绝缘电阻直接落库，覆盖修复前的老值，且只保留最新一版；
- 所有对外读数都经 ``_dump`` 从同一条落库记录上取，不存在第二份缓存。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.store import store

MODULE = "power"
REQUIRED_FIELDS = ["设备编号", "设备类型", "电压等级"]
STATUS_ORDER = ["正常", "负荷过高", "绝缘降低", "已修复"]
ACTION_RULES = {"负荷预警": "负荷过高", "绝缘报警": "绝缘降低", "安排修复": "已修复"}
REPAIR_ACTION = "安排修复"
NEGATIVE_ACTIONS = []

# 读数字段：修复回执、列表、详情和报表都只认这两个键
READING_FIELDS = ["运行负荷", "绝缘电阻"]
TRIAL_FIELD = "上次试验"

# 兼容「120」「380.5」「820kW」「0.5MΩ」这类带单位的录入
_NUMBER_RE = re.compile(r"^\s*\d+(?:\.\d+)?")

# 未补全 / 口径标注统一用这几个常量，报表和回执保持一致
SOURCE_SEED = "存量记录"
SOURCE_REPAIR = "修复录入"
UNFILLED_NOTE = "上次试验日期缺失或无法识别，读数未回填"


class ConflictError(Exception):
    """并发冲突：前端拿的版本号已过期（同一时刻重复提交修复）。"""


def _today() -> str:
    return date.today().isoformat()


def _parse_trial_date(raw: Any) -> date | None:
    """上次试验只接受 YYYY-MM-DD；存量占位文本解析不出来就返回 None。"""
    text = str(raw or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_month(raw: str | None) -> tuple[int, int]:
    text = (raw or "").strip()
    if not text:
        today = date.today()
        return today.year, today.month
    try:
        if len(text) == 7:
            year_s, month_s = text.split("-")
            year, month = int(year_s), int(month_s)
        elif len(text) >= 10:
            parsed = date.fromisoformat(text[:10])
            year, month = parsed.year, parsed.month
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError("月份格式应为 YYYY-MM，例如 2026-10") from exc
    if not 1 <= month <= 12:
        raise ValueError("月份必须在 1-12 之间")
    return year, month


class PowerService:
    # ---- 读路径：所有出口共用同一序列化，保证三处读数一致 -----------------

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
        page_rows = rows[start:start + size]
        return [self._dump(row) for row in page_rows], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self._dump(row) if row is not None else None

    def latest_readings(self) -> list[dict[str, Any]]:
        """运营概览用：设备读数只从落库记录取，每台设备永远是最新一版。"""
        return [
            {
                "id": int(row.get("id", 0)),
                "设备编号": row.get("设备编号"),
                "运行负荷": row.get("运行负荷"),
                "绝缘电阻": row.get("绝缘电阻"),
                "上次试验": row.get("上次试验"),
                "读数来源": row.get("读数来源", SOURCE_SEED),
                "status": row.get("status"),
            }
            for row in store.rows(MODULE)
        ]

    def _dump(self, row: dict[str, Any]) -> dict[str, Any]:
        """统一出口：列表、详情、动作回执、导出全部走这里，读数不可能分叉。"""
        return {
            "id": int(row.get("id", 0)),
            "status": row.get("status"),
            "pending": row.get("pending"),
            "abnormal": row.get("abnormal"),
            "设备编号": row.get("设备编号"),
            "设备类型": row.get("设备类型"),
            "电压等级": row.get("电压等级"),
            "所属区域": row.get("所属区域"),
            "运行负荷": row.get("运行负荷"),
            "绝缘电阻": row.get("绝缘电阻"),
            "上次试验": row.get("上次试验"),
            "设备状态": row.get("设备状态"),
            "读数来源": row.get("读数来源", SOURCE_SEED),
            "version": int(row.get("version", 1)),
        }

    # ---- 写路径 ---------------------------------------------------------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        with store.lock(MODULE):
            rows = store.rows(MODULE)
            entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
            entry["status"] = STATUS_ORDER[0]
            entry["pending"] = True
            entry["abnormal"] = False
            entry["version"] = 1
            rows.append(entry)
            return self._dump(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于供电系统可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        with store.lock(MODULE):
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"供电设备 {entry_id} 不存在或已归档"

            current_version = int(entry.get("version", 1))

            if action == REPAIR_ACTION:
                base_version_raw = values.get("version", values.get("base_version"))
                if str(base_version_raw or "").strip() == "":
                    return None, "修复提交缺少版本号，请刷新列表后重新安排修复"
                try:
                    base_version = int(base_version_raw)
                except (TypeError, ValueError):
                    return None, "修复提交的版本号无效，请刷新列表后重试"
                # 乐观锁放在状态判断之前：并发两次修复，先到的落库并推进 version，
                # 后到的凭旧版本号在这里被拒（409），不会进入任何写分支。
                if base_version != current_version:
                    raise ConflictError(
                        f"设备 {entry.get('设备编号', entry_id)} 的数据已被其他修复更新，"
                        "本次提交未生效，请以最新读数重新安排修复"
                    )
                # 版本号是最新的仍点修复，说明是拿着最新数据重复安排；读数只留一版
                if entry.get("status") == target:
                    return None, "该设备已完成修复，修复读数只保留最新一版，请勿重复安排"
                readings, message = self._read_repair_values(values)
                if readings is None:
                    return None, message
                # 录入读数直接落库，覆盖修复前老值；历史版本不在行上保留
                entry["运行负荷"] = readings["运行负荷"]
                entry["绝缘电阻"] = readings["绝缘电阻"]
                entry["上次试验"] = readings["上次试验"]
                entry["读数来源"] = SOURCE_REPAIR

            entry["status"] = target
            entry["pending"] = target != STATUS_ORDER[-1]
            entry["abnormal"] = action in NEGATIVE_ACTIONS
            entry["version"] = current_version + 1
            return self._dump(entry), f"供电设备已{action}"

    @staticmethod
    def _read_repair_values(
        values: dict[str, Any],
    ) -> tuple[dict[str, str] | None, str]:
        """校验并归一化修复时录入的读数；缺一个都不落库。"""
        readings: dict[str, str] = {}
        for field in READING_FIELDS:
            text = str(values.get(field) or "").strip()
            if not text:
                return None, f"修复回执缺少本次录入的{field}，请填写后再提交"
            if not _NUMBER_RE.match(text):
                return None, f"{field}「{text}」不是有效读数，应以数字开头（可带单位）"
            readings[field] = text
        trial = str(values.get(TRIAL_FIELD) or "").strip()
        if trial:
            if _parse_trial_date(trial) is None:
                return None, f"上次试验日期「{trial}」格式无效，应为 YYYY-MM-DD"
            readings[TRIAL_FIELD] = trial
        else:
            readings[TRIAL_FIELD] = _today()
        return readings, ""

    # ---- 月度试验报表 ---------------------------------------------------

    def monthly_report(self, raw_month: str | None = None) -> dict[str, Any]:
        """供电系统月度试验报表。

        旧读数沿用原有口径，按上次试验日期把存量记录回填到所属月份；
        日期缺失 / 解析不出的记录不硬凑，进 ``unfilled`` 并在报表里标注。
        """
        year, month = _parse_month(raw_month)
        items: list[dict[str, Any]] = []
        unfilled: list[dict[str, Any]] = []
        for row in sorted(store.rows(MODULE), key=lambda r: int(r.get("id", 0))):
            item = self._report_item(row)
            trial_date = _parse_trial_date(row.get(TRIAL_FIELD))
            if trial_date is None:
                item["未回填原因"] = UNFILLED_NOTE
                unfilled.append(item)
                continue
            if trial_date.year == year and trial_date.month == month:
                item["回填方式"] = (
                    "按上次试验日期回填（修复后读数）"
                    if row.get("读数来源") == SOURCE_REPAIR
                    else "按上次试验日期回填存量记录，读数沿用原有口径"
                )
                items.append(item)

        repaired = sum(1 for item in items if item["读数来源"] == SOURCE_REPAIR)
        return {
            "module": MODULE,
            "month": f"{year:04d}-{month:02d}",
            "total": len(items),
            "repaired": repaired,
            "backfilled_seed": len(items) - repaired,
            "unfilled_count": len(unfilled),
            "items": items,
            "unfilled": unfilled,
        }

    def _report_item(self, row: dict[str, Any]) -> dict[str, Any]:
        source = row.get("读数来源", SOURCE_SEED)
        return {
            "id": int(row.get("id", 0)),
            "设备编号": row.get("设备编号"),
            "设备类型": row.get("设备类型"),
            "电压等级": row.get("电压等级"),
            "所属区域": row.get("所属区域"),
            "运行负荷": row.get("运行负荷"),
            "绝缘电阻": row.get("绝缘电阻"),
            "上次试验": row.get("上次试验"),
            "设备状态": row.get("status"),
            "读数来源": source,
            "读数备注": (
                "修复后录入的最新读数"
                if source == SOURCE_REPAIR
                else "存量记录，沿用原有口径"
            ),
        }
