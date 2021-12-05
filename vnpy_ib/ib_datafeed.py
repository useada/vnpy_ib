from datetime import timedelta, datetime as _datetime, date as _date, time as _time
from pytz import timezone
from typing import Dict, List, Optional
from copy import deepcopy

import pandas as pd
# import tushare as ts
from ib_insync import *

from pytz import BaseTzInfo
from tzlocal import get_localzone

from vnpy.trader.setting import SETTINGS
from vnpy.trader.datafeed import BaseDatafeed
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, HistoryRequest
from vnpy.trader.utility import round_to

# 数据频率映射
INTERVAL_VT2IB = {
    Interval.MINUTE: "1 min",
    Interval.HOUR: "1 hour",
    Interval.DAILY: "1 day",
}

# A股票交易所列表
STOCK_LIST = [
    Exchange.SSE,
    Exchange.SZSE,
]

# 美股交易所列表
US_STOCK_LIST = [
    Exchange.NASDAQ,
    Exchange.SMART,
    Exchange.NYSE,
]

# 期货支持列表
FUTURE_LIST = [
    Exchange.CFFEX,
    Exchange.SHFE,
    Exchange.CZCE,
    Exchange.DCE,
    Exchange.INE,
]

# 交易所映射
EXCHANGE_VT2IB = {
    Exchange.CFFEX: "CFX",
    Exchange.SHFE: "SHF",
    Exchange.CZCE: "ZCE",
    Exchange.DCE: "DCE",
    Exchange.INE: "INE",
    Exchange.SSE: "SH",
    Exchange.SZSE: "SZ",
    Exchange.NASDAQ: "NASDAQ",
}

# 时间调整映射
INTERVAL_ADJUSTMENT_MAP = {
    Interval.MINUTE: timedelta(minutes=1),
    Interval.HOUR: timedelta(hours=1),
    Interval.DAILY: timedelta()
}

# 中国上海时区
CHINA_TZ = timezone("Asia/Shanghai")


# def to_ib_symbol(symbol, exchange) -> Optional[str]:
#     """将交易所代码转换为ib代码"""
#     # 股票
#     if exchange in US_STOCK_LIST:
#         ts_symbol = f"{symbol}.{EXCHANGE_VT2TS[exchange]}"
#     # 期货
#     elif exchange in FUTURE_LIST:
#         ts_symbol = f"{symbol}.{EXCHANGE_VT2TS[exchange]}".upper()
#     elif exchange in US_STOCK_LIST:
#         ts_symbol = symbol
#     else:
#         return None

#     return ts_symbol


# def to_ts_asset(symbol, exchange) -> Optional[str]:
#     """生成tushare资产类别"""
#     # 股票
#     if exchange in STOCK_LIST:
#         if exchange is Exchange.SSE and symbol[0] == "6":
#             asset = "E"
#         elif exchange is Exchange.SZSE and symbol[0] == "0" or symbol[0] == "3":
#             asset = "E"
#         else:
#             asset = "I"
#     # 期货
#     elif exchange in FUTURE_LIST:
#         asset = "FT"
#     elif exchange in US_STOCK_LIST:
#         asset = "E"
#     else:
#         return None

#     return asset


class IbDatafeed(BaseDatafeed):
    """ib 数据服务接口"""

    local_tz: BaseTzInfo = get_localzone()

    def __init__(self):
        """"""
        self.username: str = SETTINGS["datafeed.username"]
        self.password: str = SETTINGS["datafeed.password"]

        self.inited: bool = False

    def init(self) -> bool:
        """初始化"""
        if self.inited:
            return True

        self.ib = IB()
        self.ib.connect('127.0.0.1', 7496, clientId=1)

        self.inited = True
        return True

    def query_bar_history(self, req: HistoryRequest) -> Optional[List[BarData]]:
        """查询k线数据"""
        if not self.inited:
            self.init()

        symbol = req.symbol
        exchange = EXCHANGE_VT2IB.get(req.exchange)
        if not exchange:
            return None
        adjustment = INTERVAL_ADJUSTMENT_MAP[req.interval]
        interval = INTERVAL_VT2IB.get(req.interval)
        if not interval:
            return None

        # start = req.start.strftime("%Y%m%d")
        # end = req.end.strftime("%Y%m%d")
        start = req.start
        end = req.end

        if req.exchange == Exchange.IDEALPRO:
            bar_type: str = "MIDPOINT"
        else:
            bar_type: str = "TRADES"

        contract = Stock(symbol=symbol, exchange=exchange, currency="USD")
        # contract = Stock('AMD', 'SMART', 'USD')
        # contract = Forex('EURUSD')
        bars = self.ib.reqHistoricalData(
            contract, endDateTime=end, durationStr='30 D',
            barSizeSetting=interval, whatToShow=bar_type, useRTH=True)

        # convert to pandas dataframe:
        df = util.df(bars)
        print(df)

        bar_keys: List[_datetime] = []
        bar_dict: Dict[_datetime, BarData] = {}
        data: List[BarData] = []

        # 处理原始数据中的NaN值
        df.fillna(0, inplace=True)

        if df is not None:
            for ix, row in df.iterrows():
                if row["open"] is None:
                    continue

                # if interval.value == "d":
                #     dt = row["trade_date"]
                #     dt = datetime.strptime(dt, "%Y%m%d")
                # else:
                #     dt = row["trade_time"]
                #     dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S") - adjustment

                date = row["date"]
                # if len(date) > 8:
                #     dt: datetime = datetime.strptime(date, "%Y%m%d %H:%M:%S")
                # else:
                #     dt: datetime = datetime.strptime(date, "%Y%m%d")
                if type(date) == _date:
                    dt = _datetime.combine(date=date, time=_time.min)
                    # s=date.strftime('%Y/%m/%d')
                    # # dt = _datetime.strptime('2017/02/04 20:49', '%Y/%m/%d %H:%M')
                    # dt = _datetime.strptime(s, '%Y/%m/%d')
                else:
                    # dt: _datetime = CHINA_TZ.localize(date)
                    local_tz: BaseTzInfo = get_localzone()
                    dt: _datetime = self.local_tz.localize(date)

                bar: BarData = BarData(
                    symbol=req.symbol,
                    exchange=req.exchange,
                    interval=req.interval,
                    datetime=dt,
                    open_price=round_to(row["open"], 0.000001),
                    high_price=round_to(row["high"], 0.000001),
                    low_price=round_to(row["low"], 0.000001),
                    close_price=round_to(row["close"], 0.000001),
                    volume=row["volume"],
                    gateway_name="IB"
                )

                bar_dict[dt] = bar

        bar_keys = bar_dict.keys()
        bar_keys = sorted(bar_keys, reverse=False)
        for i in bar_keys:
            data.append(bar_dict[i])

        return data


        # ib_contract: Contract = generate_ib_contract(req.symbol, req.exchange)

        # if req.end:
        #     end: datetime = req.end
        #     end_str: str = end.strftime("%Y%m%d %H:%M:%S")
        # else:
        #     end: datetime = datetime.now(self.local_tz)
        #     end_str: str = ""

        # delta: timedelta = end - req.start
        # days: int = min(delta.days, 180)     # IB 只提供6个月数据
        # duration: str = f"{days} D"
        # bar_size: str = INTERVAL_VT2IB[req.interval]

        # if req.exchange == Exchange.IDEALPRO:
        #     bar_type: str = "MIDPOINT"
        # else:
        #     bar_type: str = "TRADES"

        # self.history_reqid = self.reqid
        # self.client.reqHistoricalData(
        #     self.reqid,
        #     ib_contract,
        #     end_str,
        #     duration,
        #     bar_size,
        #     bar_type,
        #     0,
        #     1,
        #     False,
        #     []
        # )

        # self.history_condition.acquire()    # 等待异步数据返回
        # self.history_condition.wait()
        # self.history_condition.release()

        # history: List[BarData] = self.history_buf
        # self.history_buf: List[BarData] = []       # 创新新的缓冲列表
        # self.history_req: HistoryRequest = None

        # return history


        # ts_symbol = to_ts_symbol(symbol, exchange)
        # if not ts_symbol:
        #     return None

        # asset = to_ts_asset(symbol, exchange)
        # if not asset:
        #     return None

        # ts_interval = INTERVAL_VT2TS.get(interval)
        # if not ts_interval:
        #     return None

        # adjustment = INTERVAL_ADJUSTMENT_MAP[interval]

        # d1 = ts.pro_bar(
        #     ts_code=ts_symbol,
        #     start_date=start,
        #     end_date=end,
        #     asset=asset,
        #     freq=ts_interval
        # )
        # df = deepcopy(d1)

        # while True:
        #     if len(d1) != 8000:
        #         break
        #     tmp_end = d1["trade_time"].values[-1]

        #     d1 = ts.pro_bar(
        #         ts_code=ts_symbol,
        #         start_date=start,
        #         end_date=tmp_end,
        #         asset=asset,
        #         freq=ts_interval
        #     )
        #     df = pd.concat([df[:-1], d1])

        # bar_keys: List[datetime] = []
        # bar_dict: Dict[datetime, BarData] = {}
        # data: List[BarData] = []

        # # 处理原始数据中的NaN值
        # df.fillna(0, inplace=True)

        # if df is not None:
        #     for ix, row in df.iterrows():
        #         if row["open"] is None:
        #             continue

        #         if interval.value == "d":
        #             dt = row["trade_date"]
        #             dt = datetime.strptime(dt, "%Y%m%d")
        #         else:
        #             dt = row["trade_time"]
        #             dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S") - adjustment

        #         dt = CHINA_TZ.localize(dt)

        #         bar: BarData = BarData(
        #             symbol=symbol,
        #             exchange=exchange,
        #             interval=interval,
        #             datetime=dt,
        #             open_price=round_to(row["open"], 0.000001),
        #             high_price=round_to(row["high"], 0.000001),
        #             low_price=round_to(row["low"], 0.000001),
        #             close_price=round_to(row["close"], 0.000001),
        #             volume=row["vol"],
        #             turnover=row.get("amount", 0),
        #             open_interest=row.get("oi", 0),
        #             gateway_name="TS"
        #         )

        #         bar_dict[dt] = bar

        # bar_keys = bar_dict.keys()
        # bar_keys = sorted(bar_keys, reverse=False)
        # for i in bar_keys:
        #     data.append(bar_dict[i])

        # return data

if __name__ == '__main__':
    datafeed = IbDatafeed2()
    datafeed.init()
    start = _datetime.strptime('2021/02/04 00:00', '%Y/%m/%d %H:%M')
    req = HistoryRequest(symbol="JD", exchange=Exchange.NASDAQ,
        start=start, interval=Interval.DAILY)
    print (datafeed.query_bar_history(req))