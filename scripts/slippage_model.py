"""A股回测成本与滑点模型 — TG-TRADING-SYS-V1 决策森林回测（df_backtest.py）参考实现。

纯 stdlib，零第三方依赖。设计规格见 docs/TG-TRADING-SYS-V1-设计文档.md §7.1.3。
成本/滑点参数借鉴 KHQuant 的 A 股建模，此处按 V1 需求重写（非 MiniQMT 依赖）。

成交流程：委托价 → 滑点 → 成交价 → 成交金额 → 费用(佣金/印花税/过户费) → 净现金流
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostModel:
    """交易成本参数，默认值按当前 A 股市场（2026）。"""

    commission_rate: float = 0.0001  # 佣金比例（万1）
    min_commission: float = 5.0      # 最低佣金（元）
    stamp_tax: float = 0.0005        # 印花税（卖出单边，0.05%）
    transfer_fee: float = 0.0        # 过户费（现行 0.00001 双边，量级可忽略，默认关）
    slippage_type: str = "ratio"     # 'ratio' 按成交额比例 | 'tick' 按最小变动价位
    slippage: float = 0.001          # ratio=双边总滑点比例(0.001=0.1%)；tick=价位个数

    def fill_price(self, order_price: float, side: str) -> float:
        """滑点后成交价。side: 'buy' 上浮 / 'sell' 下浮，均取对己方不利方向。"""
        assert side in ("buy", "sell"), side
        if self.slippage_type == "ratio":
            half = self.slippage / 2
            p = order_price * (1 + half) if side == "buy" else order_price * (1 - half)
        else:  # tick：A股最小变动价位 0.01 元
            shift = self.slippage * 0.01
            p = order_price + shift if side == "buy" else order_price - shift
        # ponytail: float round 到分，x.xx5 边界差 1 分，回测可忽略；实盘资金再换 Decimal
        return round(p, 2)

    def fees(self, amount: float, side: str) -> float:
        """成交金额 amount 对应的总费用：佣金(≥最低5元) + 印花税(仅卖出) + 过户费。"""
        commission = max(amount * self.commission_rate, self.min_commission)
        stamp = amount * self.stamp_tax if side == "sell" else 0.0
        transfer = amount * self.transfer_fee
        return commission + stamp + transfer

    def cash_flow(self, order_price: float, shares: int, side: str) -> float:
        """净现金流：buy 为负（支付），sell 为正（收入），已含滑点与全部费用。"""
        price = self.fill_price(order_price, side)
        amount = price * shares
        total = amount + self.fees(amount, side)
        return -total if side == "buy" else total


def round_lot_return(buy_price: float, sell_price: float, shares: int,
                     model: CostModel) -> float:
    """一次完整买卖的收益率：(卖出净收入 - 买入净支出) / 买入净支出。"""
    out = -model.cash_flow(buy_price, shares, "buy")   # 买入净支出
    inn = model.cash_flow(sell_price, shares, "sell")  # 卖出净收入
    return (inn - out) / out


def demo():
    m = CostModel()

    # tick 滑点：买 10.00 + 1 tick = 10.01，卖 10.00 - 1 tick = 9.99
    mt = CostModel(slippage_type="tick", slippage=1)
    assert mt.fill_price(10.0, "buy") == 10.01
    assert mt.fill_price(10.0, "sell") == 9.99

    # ratio 滑点：买 20.00 → 20.01，卖 20.00 → 19.99（避开 x.xx5 浮点边界）
    assert m.fill_price(20.0, "buy") == 20.01
    assert m.fill_price(20.0, "sell") == 19.99

    # 佣金最低 5 元：1000 元小单 → 佣金 0.1 → 收 5 元
    assert m.fees(1000.0, "buy") == 5.0
    # 卖出含印花税：10 万元 → 佣金 10 + 印花税 50 = 60
    assert abs(m.fees(100000.0, "sell") - 60.0) < 1e-9

    # 零滑点零成本：收益率应等于裸价差
    m0 = CostModel(slippage=0.0, commission_rate=0.0, min_commission=0.0,
                   stamp_tax=0.0, transfer_fee=0.0)
    assert abs(round_lot_return(10.0, 11.0, 1000, m0) - 0.10) < 1e-9

    print("slippage_model 自检通过")


if __name__ == "__main__":
    demo()
