import os
import sys
import time
from datetime import datetime

# 将项目根目录添加到路径中，确保能导入模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from data_manager import get_data_manager
import config
import pandas as pd
import pymysql
import json

def get_market_minutes():
    """获取当日已交易分钟数"""
    now = datetime.now()
    # 09:30 - 11:30 (120 min)
    # 13:00 - 15:00 (120 min)
    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        return 0
    elif now.hour < 11 or (now.hour == 11 and now.minute <= 30):
        return (now.hour - 9) * 60 + now.minute - 30
    elif now.hour < 13:
        return 120
    elif now.hour < 15:
        return 120 + (now.hour - 13) * 60 + now.minute
    else:
        return 240

def get_display_width(s):
    """计算字符串的显示宽度（中文占2单位，英文占1单位）"""
    return len(s) + sum(1 for char in s if '\u4e00' <= char <= '\u9fff')

def pad_str(s, width):
    """对含有中文的字符串进行对齐填充"""
    return s + ' ' * (width - get_display_width(s))

def select_stocks_by_change():
    """
    获取今天涨幅在 3% 到 5% 之间的股票
    """
    # 1. 初始化数据管理器
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在连接行情接口...")
    dm = get_data_manager()
    
    if not dm.xt:
        print("错误: 无法连接到行情服务，请确保 QMT 客户端已启动并登录。")
        return

    # 2. 获取股票列表
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在获取全市场股票列表...")
    try:
        # 获取沪深A股板块下的所有股票代码
        # 注意: 不同版本的 QMT 可能对板块名称的支持有所不同
        sector_name = '沪深A股'
        stock_list = dm.xt.get_stock_list_in_sector(sector_name)
        
        # 如果获取不到，尝试兼容性板块名
        if not stock_list:
            print(f"尝试从 '{sector_name}' 获取为空，正在尝试替代板块...")
            for alt_sector in ['沪深主板', 'A股', '上证A股', '深证A股']:
                alt_list = dm.xt.get_stock_list_in_sector(alt_sector)
                if alt_list:
                    print(f"从 '{alt_sector}' 获取到数据")
                    stock_list.extend(alt_list)
            
            # 去重
            stock_list = list(set(stock_list))
            
        # 根据 bk_stock_link 表进行过滤
        if stock_list:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在根据数据库进行股票过滤...")
            try:
                config_path = os.path.join(os.path.dirname(__file__), 'test_get_config.json')
                with open(config_path, 'r', encoding='utf-8') as f:
                    app_config = json.load(f)
                db_config = app_config['db']
                
                conn = pymysql.connect(**db_config)
                cursor = conn.cursor()
                now_dt = datetime.now()
                table_name = f"bk_stock_link_{now_dt.strftime('%Y%m')}"
                
                # 获取最新可用日期，解决当天无数据时过滤为空的问题
                cursor.execute(f"SELECT MAX(date) FROM {table_name}")
                max_date_res = cursor.fetchone()
                if max_date_res and max_date_res[0]:
                    current_date = max_date_res[0]
                else:
                    current_date = now_dt.strftime('%Y-%m-%d')
                
                print(f"使用日期 {current_date} 的数据进行过滤...")
                sql = f"SELECT code FROM {table_name} WHERE date = %s"
                cursor.execute(sql, (current_date,))
                rows = cursor.fetchall()
                allowed_codes = set(row[0] for row in rows)
                conn.close()
                
                filtered_list = [stock for stock in stock_list if stock.split('.')[0] in allowed_codes]
                print(f"数据库过滤完成: 原有 {len(stock_list)} 只，过滤后剩余 {len(filtered_list)} 只。")
                stock_list = filtered_list
            except Exception as e:
                print(f"数据库过滤出错: {e}")

        if not stock_list:
            print("未能获取到任何股票列表。请检查 QMT 客户端是否正常连接。")
            return
            
        print(f"共获取到 {len(stock_list)} 只候选股票。")
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        return

    # 3. 建立板块映射 (从数据库)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在建立行业板块映射...")
    industry_map = {}
    
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'test_get_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            app_config = json.load(f)
        db_config = app_config['db']
        
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()
        now_dt = datetime.now()
        table_name = f"bk_stock_link_{now_dt.strftime('%Y%m')}"
        
        sql = f"SELECT DISTINCT bkname, code FROM {table_name}"
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        
        # 构建 code 到 bkname 的映射
        code_to_bk = {}
        for bkname, code in rows:
            if code not in code_to_bk:
                code_to_bk[code] = []
            code_to_bk[code].append(bkname)
            
        # 根据 stock_list 构建最终的 industry_map
        for stock in stock_list:
            base_code = stock.split('.')[0]
            if base_code in code_to_bk:
                industry_map[stock] = ",".join(code_to_bk[base_code])
                
    except Exception as e:
        print(f"建立板块映射失败: {e}")

    # 4. 初始化历史数据缓存变量 (在循环中为符合初筛条件的股票下载)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 准备进行指标筛选...")
    minutes_passed = get_market_minutes()
    
    # 获取成交量基准 (依然尝试全局获取一次，如果失败则在循环中单独下载)
    avg_vols = pd.Series()
    try:
        # 尝试获取过去5天的成交量
        history_vols_data = dm.xt.get_market_data(field_list=['volume'], stock_list=stock_list, period='1d', count=5)
        if 'volume' in history_vols_data:
            avg_vols = history_vols_data['volume'].mean(axis=1)
    except:
        pass

    # 5. 获取全量行情快照
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在获取全市场实时行情...")

    try:
        full_ticks = dm.xt.get_full_tick(stock_list)
        if not full_ticks:
            print("未能获取到行情快照，请检查 QMT 状态。")
            return
            
        print(f"成功获取 {len(full_ticks)} 只股票的实时行情数据。")
    except Exception as e:
        print(f"获取行情数据失败: {e}")
        return

    # 4. 筛选符合条件的股票
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在计算指标并筛选目标股票...")
    selected_stocks = []
    
    for code, tick in full_ticks.items():
        try:
                
            last_price = tick.get('lastPrice', 0)
            pre_close = tick.get('lastClose', 0)
            volume = tick.get('volume', 0)
            amount = tick.get('amount', 0)
            
            # 1. 基础条件筛选 (价格/涨幅)
            if last_price <= 0 or pre_close <= 0: continue
            change_pct = (last_price - pre_close) / pre_close * 100
            if not (3.0 <= change_pct <= 5.0): continue

            # 2. 排除 ST 股
            name = dm.stock_names_cache.get(code)
            if not name:
                detail = dm.xt.get_instrument_detail(code)
                name = detail.get('InstrumentName') or detail.get('instrumentName') or '未知'
                dm.stock_names_cache[code] = name
            
            if 'ST' in name.upper():
                continue

            # 3. 换手率筛选 [5%-10%]
            detail = dm.xt.get_instrument_detail(code)
            float_volume = detail.get('FloatVolume', 0)
            turnover_rate = 0
            if float_volume > 0:
                turnover_rate = (volume * 100 / float_volume) * 100
            if not (5.0 <= turnover_rate <= 10.0): continue
            
            # 4. 市值筛选 [100亿 - 300亿]
            # TotalVolume 通常为总股本（股）
            total_shares = detail.get('TotalVolume', detail.get('TotalCapital', 0))
            market_cap_billion = (total_shares * last_price) / 1e8
            if not (100.0 <= market_cap_billion <= 300.0): continue
            
            # 5. 量比筛选 > 1
            avg_daily_vol = avg_vols.get(code, 0)
            if pd.isna(avg_daily_vol):
                avg_daily_vol = 0
                
            vol_ratio = 0
            if avg_daily_vol > 0 and minutes_passed > 0:
                vol_ratio = (volume / minutes_passed) / (avg_daily_vol / 240)
            elif avg_daily_vol == 0 and volume > 0:
                vol_ratio = 1.01 # 容错
            if vol_ratio <= 1.0: continue

            # 6. 当前股价 > 今日均线
            today_avg_price = amount / (volume * 100) if volume > 0 else 0
            if last_price <= today_avg_price: continue

            # 7. MA5 相关条件 (按需下载历史数据)
            # 检查本地是否有该股的收盘价历史
            # 如果没有，尝试为该股下载最近的日线数据
            hist_closes = []
            try:
                # 尝试获取
                h_data = dm.xt.get_market_data(field_list=['close'], stock_list=[code], period='1d', count=6)
                if 'close' in h_data and not h_data['close'].empty:
                    hist_closes = h_data['close'].iloc[0].dropna().values
                
                # 如果获取不到或不足，执行下载
                if len(hist_closes) < 5:
                    dm.xt.download_history_data(code, period='1d', start_time='', end_time='')
                    # 重新获取
                    h_data = dm.xt.get_market_data(field_list=['close'], stock_list=[code], period='1d', count=6)
                    if 'close' in h_data and not h_data['close'].empty:
                        hist_closes = h_data['close'].iloc[0].dropna().values
            except:
                pass

            if len(hist_closes) >= 5:
                # 今天的 MA5 (使用实时价替代今天未收盘的 Close)
                # hist_closes 的顺序通常是升序 [T-5, T-4, T-3, T-2, T-1]
                ma5_today = (last_price + sum(hist_closes[-4:])) / 5
                # 昨天的 MA5
                ma5_yesterday = sum(hist_closes[-5:]) / 5
                
                # 条件: 股价 > MA5
                if last_price <= ma5_today: continue
                
                # 条件: MA5 上移
                if ma5_today <= ma5_yesterday: continue
            else:
                continue

            # 获取板块信息
            industry = industry_map.get(code, "其他")
            
            selected_stocks.append({
                'code': code,
                'name': name,
                'industry': industry,
                'price': last_price,
                'change': change_pct,
                'turnover': turnover_rate,
                'vol_ratio': vol_ratio,
                'market_cap': market_cap_billion,
                'amount': amount
            })
        except Exception:
            continue

    # 6. 输出结果
    # 按照成交额 (amount) 从大到小排名
    selected_stocks.sort(key=lambda x: x['amount'], reverse=True)
    
    print("\n" + "="*115)
    print(f"筛选结果: 涨幅[3-5%] | 换手[5-10%] | 市值[100-300亿] | 量比>1 | 股价>均线/MA5 | MA5上行 | 非ST | 共 {len(selected_stocks)} 只")
    print("-" * 115)
    
    header = (
        pad_str("代码", 11) + 
        pad_str("名称", 12) + 
        pad_str("申万二级板块", 20) + 
        pad_str("价格", 8) + 
        pad_str("涨幅", 10) + 
        pad_str("换手率", 10) + 
        pad_str("量比", 8) + 
        pad_str("市值(亿)", 12) + 
        pad_str("成交额(万)", 12)
    )
    print(header)
    print("-" * 115)
    
    display_limit = 100
    display_count = 0
    
    for s in selected_stocks:
        name_str = s['name'][:6]
        ind_str = s['industry'][:8]
        amount_wan = s['amount'] / 10000
        
        row = (
            pad_str(s['code'], 11) + 
            pad_str(name_str, 12) + 
            pad_str(ind_str, 20) + 
            f"{s['price']:<8.2f} " + 
            f"{s['change']:>7.2f}%   " + 
            f"{s['turnover']:>7.2f}%   " + 
            f"{s['vol_ratio']:>6.2f}   " + 
            f"{s['market_cap']:>8.1f}    " + 
            f"{amount_wan:>10.0f}"
        )
        print(row)
        display_count += 1
        if display_count >= display_limit:
            print(f"... (更多 {len(selected_stocks) - display_limit} 只结果已省略)")
            break
            
    print("="*115)
    print(f"筛选完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"提示: 当前计算量比使用的分钟数为 {minutes_passed} 分钟。")
    if any(s['vol_ratio'] == 1.01 for s in selected_stocks):
        print("注意: 部分量比显示为 1.01 是因为本地缺少历史成交量数据，已为您默认通过筛选。")
        print("建议: 您可以使用 DataManager 的 download_history_data 方法下载全市场历史日线数据以获得准确量比。")

if __name__ == "__main__":
    # 执行筛选
    try:
        select_stocks_by_change()
    except KeyboardInterrupt:
        print("\n用户取消操作。")
    except Exception as e:
        print(f"\n执行过程中发生错误: {e}")
