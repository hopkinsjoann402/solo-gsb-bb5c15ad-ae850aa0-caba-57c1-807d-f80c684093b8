"""API 数据模型。金额一律以 *字符串* 收发，杜绝 float 精度问题。"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$|^-?\.\d+$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UTC_SECOND_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_UTC_SECOND_FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_iso_date(value: str, field: str = "日期") -> date:
    """严格解析 ISO 8601 **日期**（YYYY-MM-DD）。

    只接受日期形状，拒绝带时间的字符串（如 ``2026-09-23T00:00:00Z``）与
    不存在的日期（如 ``2026-02-30``）；失败抛 ``ValueError``（API 层映射为 422）。
    """

    text = value.strip()
    if not _ISO_DATE_RE.match(text):
        raise ValueError(f"{field} 必须是 ISO 日期（YYYY-MM-DD），收到 {value!r}")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} 不是合法日期（YYYY-MM-DD），收到 {value!r}") from exc


def parse_utc_second(value: str, field: str = "at") -> datetime:
    """严格解析 UTC **秒精度**时间（``YYYY-MM-DDTHH:MM:SSZ``）。

    只接受字面 ``Z`` 结尾、无毫秒/微秒/时区偏移的 UTC 秒精度形状；
    不存在的日期/时间（如 ``2026-02-30T12:00:00Z``、``2026-09-23T24:00:00Z``）
    同样拒绝。返回时区感知的 UTC ``datetime``；失败抛 ``ValueError``
    （API 层映射为 422）。
    """

    text = value.strip()
    if not _UTC_SECOND_RE.match(text):
        raise ValueError(
            f"{field} 必须是 UTC 秒精度时间（YYYY-MM-DDTHH:MM:SSZ），收到 {value!r}"
        )
    try:
        parsed = datetime.strptime(text, _UTC_SECOND_FMT)
    except ValueError as exc:
        raise ValueError(
            f"{field} 不是合法的 UTC 秒精度时间（YYYY-MM-DDTHH:MM:SSZ），收到 {value!r}"
        ) from exc
    return parsed.replace(tzinfo=timezone.utc)


def format_utc_second(value: datetime) -> str:
    """时区感知 datetime -> 规范化的 UTC 秒精度字符串（``...Z``，无小数秒）。"""

    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class LineIn(BaseModel):
    description: str | None = Field(default=None, max_length=500)
    net: str = Field(description="不含税净额，币种最小单位的整数倍，如 '100.00'")
    tax_rate: str = Field(description="税率，0~1 的小数字符串，如 '0.13'")

    @field_validator("net", "tax_rate")
    @classmethod
    def _check_decimal(cls, v: str, info: Any) -> str:
        v = v.strip()
        if not _DECIMAL_RE.match(v):
            raise ValueError(f"{info.field_name} 必须是十进制数字字符串，收到 {v!r}")
        return v


class InvoiceCreate(BaseModel):
    currency: str = Field(description="发票币种 ISO 4217 代码，如 USD / CNY / JPY")
    lines: list[LineIn] = Field(min_length=1)
    target_currency: str | None = Field(
        default=None, description="可选：换算目标币种；提供时必须同时给 exchange_rate"
    )
    exchange_rate: str | None = Field(
        default=None, description="汇率，1 单位发票币种 = exchange_rate 单位目标币种"
    )
    due_date: str | None = Field(
        default=None, description="可选：到期日，ISO 8601 日期 YYYY-MM-DD（如 '2026-10-01'）"
    )

    @field_validator("currency", "target_currency")
    @classmethod
    def _upper_currency(cls, v: str | None) -> str | None:
        return v.upper().strip() if v is not None else None

    @field_validator("due_date")
    @classmethod
    def _check_due_date(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return parse_iso_date(v, "due_date").isoformat()

    @field_validator("exchange_rate")
    @classmethod
    def _check_rate(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not _DECIMAL_RE.match(v):
            raise ValueError(f"exchange_rate 必须是十进制数字字符串，收到 {v!r}")
        return v


# ---- 出参（宽松模型，extra 允许，主要服务于 OpenAPI 文档）----

class AllocationOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    line_no: int
    delta_units: int
    remainder: str
    rank: int


class RoundingOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    mode: str
    minor_unit: str
    residual_units: int
    residual_amount: str
    method: str
    allocations: list[AllocationOut]


class ConvertedLineOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    currency: str
    net: str
    tax: str
    gross: str


class LineOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    line_no: int
    description: str | None = None
    tax_rate: str
    currency: str
    net: str
    exact_tax: str
    tax: str
    gross: str
    converted: ConvertedLineOut | None = None


class TotalsOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    currency: str
    total_net: str
    total_tax: str
    total_gross: str


class FxOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    target_currency: str
    target_digits: int
    exchange_rate: str
    rate_direction: str
    total_net: str
    total_tax: str
    total_gross: str
    residual_units: int
    residual_unit: str
    allocations: list[AllocationOut]


class InvoiceResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    rule_id: str
    currency: str
    currency_digits: int
    lines: list[LineOut]
    totals: TotalsOut
    rounding: RoundingOut
    fx: FxOut | None = None
    due_date: str | None = None
    created_at: str
    recompute_matched: bool


class InvoiceSummary(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    currency: str
    target_currency: str | None = None
    total_net: str
    total_tax: str
    total_gross: str
    line_count: int
    created_at: str


class PagedInvoices(BaseModel):
    items: list[InvoiceSummary]
    page: int
    page_size: int
    total: int
    pages: int


class Health(BaseModel):
    status: str
    database: str


# ---- 收款登记 ----

class PaymentCreate(BaseModel):
    amount: str = Field(
        description="收款金额，发票币种的十进制字符串，必须大于 0 且为币种最小单位的整数倍，如 '33.11'"
    )

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, v: str) -> str:
        v = v.strip()
        if not _DECIMAL_RE.match(v):
            raise ValueError(f"amount 必须是十进制数字字符串，收到 {v!r}")
        return v


class PaymentOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    invoice_id: int
    amount: str
    currency: str
    created_at: str
    reversed_total: str
    net_amount: str


class PaymentResult(PaymentOut):
    """登记收款成功后的响应：收款记录 + 最新余额。"""

    paid_total: str
    outstanding: str


class PaymentAllocationCreate(BaseModel):
    """一笔来款在多张同币种待结发票间的分配请求。"""

    currency: str = Field(
        description="来款币种 ISO 4217 代码；只分配给同币种发票，不做跨币种换算，如 USD / JPY"
    )
    amount: str = Field(
        description="来款总金额，十进制字符串，必须大于 0 且为币种最小单位的整数倍，如 '100.00'"
    )
    invoice_ids: list[int] = Field(
        min_length=1,
        description="待结发票 ID 列表，不得重复；只处理列表内发票，"
        "实际按到期日升序（无到期日排最后）、同日按 ID 升序逐张抵扣",
    )

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, v: str) -> str:
        v = v.strip()
        if not _DECIMAL_RE.match(v):
            raise ValueError(f"amount 必须是十进制数字字符串，收到 {v!r}")
        return v

    @field_validator("invoice_ids")
    @classmethod
    def _check_invoice_ids(cls, v: list[int]) -> list[int]:
        for invoice_id in v:
            if invoice_id <= 0:
                raise ValueError(f"invoice_ids 必须是正整数，收到 {invoice_id}")
        if len(v) != len(set(v)):
            raise ValueError(f"invoice_ids 不得包含重复的发票 ID，收到 {v}")
        return v


class PaymentAllocationItem(BaseModel):
    """单张发票在本次来款中的分配结果（按实际抵扣顺序排列）。"""

    model_config = ConfigDict(extra="allow")
    invoice_id: int
    due_date: str | None = None
    allocated: str
    outstanding: str
    payment_id: int | None = None


class PaymentAllocationResult(BaseModel):
    """来款分配成功后的响应：逐发票分配金额与剩余余额。"""

    model_config = ConfigDict(extra="allow")
    currency: str
    amount: str
    allocated_total: str
    created_at: str
    allocations: list[PaymentAllocationItem]


class PaymentOverview(BaseModel):
    """按发票查询的收款记录与未收余额（余额按净入账额 = 收款 − 冲销 计算）。"""

    model_config = ConfigDict(extra="allow")
    invoice_id: int
    currency: str
    total_gross: str
    paid_total: str
    reversed_total: str
    outstanding: str
    payment_count: int
    payments: list[PaymentOut]


# ---- 收款冲销 ----

class ReversalCreate(BaseModel):
    amount: str = Field(
        description="本次冲销金额，发票币种的十进制字符串；必须大于 0、为币种最小单位的整数倍，"
        "且与历史冲销累计不得超过原收款金额，如 '5.00'"
    )

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, v: str) -> str:
        v = v.strip()
        if not _DECIMAL_RE.match(v):
            raise ValueError(f"amount 必须是十进制数字字符串，收到 {v!r}")
        return v


class ReversalResult(BaseModel):
    """冲销成功后的响应：冲销记录 + 原流水的累计冲销与净入账额。"""

    model_config = ConfigDict(extra="allow")
    id: int
    payment_id: int
    invoice_id: int
    amount: str
    currency: str
    created_at: str
    reversed_total: str
    net_amount: str


# ---- 逾期查询 ----


class OverdueInvoice(BaseModel):
    """逾期发票条目：到期日早于 as_of 且仍有未收余额。"""

    model_config = ConfigDict(extra="allow")
    id: int
    currency: str
    due_date: str
    total_gross: str
    paid_total: str
    outstanding: str
    created_at: str


class PagedOverdueInvoices(BaseModel):
    items: list[OverdueInvoice]
    page: int
    page_size: int
    total: int
    pages: int
    as_of: str


# ---- 历史收款快照 ----


class SnapshotPaymentOut(BaseModel):
    """快照时点已登记（且在截止时点之前/当秒）的收款流水。"""

    model_config = ConfigDict(extra="allow")
    id: int
    invoice_id: int
    amount: str
    currency: str
    created_at: str
    # 截止时点前该流水已发生的冲销合计（注意：可能小于当前实时值）
    reversed_total: str
    # 截止时点的净入账额 = amount − 截止时点的 reversed_total
    net_amount: str


class SnapshotReversalOut(BaseModel):
    """快照时点之前/当秒已发生的冲销流水。"""

    model_config = ConfigDict(extra="allow")
    id: int
    payment_id: int
    amount: str
    created_at: str


class PaymentSnapshot(BaseModel):
    """单张发票在某个历史时点（UTC 秒精度，截止秒闭区间）的收款快照。

    只统计 ``created_at <= at`` 的收款与对应冲销；截止时点之后登记的流水
    不参与计算，因此同一历史时点的结果不会随后续收款/冲销改变。
    """

    model_config = ConfigDict(extra="allow")
    invoice_id: int
    currency: str
    at: str
    invoice_created_at: str
    total_gross: str
    paid_total: str        # 收款总额（截止时点前/当秒收款的毛额合计）
    reversed_total: str    # 冲销总额（截止时点前/当秒冲销合计）
    net_paid: str          # 净已收 = paid_total − reversed_total
    outstanding: str       # 未收余额 = total_gross − net_paid
    payment_count: int
    reversal_count: int
    payments: list[SnapshotPaymentOut]
    reversals: list[SnapshotReversalOut]
