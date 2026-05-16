import requests
import time
import json
import math
import re
import pymysql
import random
from datetime import datetime

# 数据库配置信息
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'system',
    'database': 'qstock',
    'charset': 'utf8mb4'
}

# 全局配置变量
now = datetime.now()
TABLE_NAME = f"bk_stock_link_{now.strftime('%Y%m')}"  # 目标表名
FIXED_DATE = now.strftime('%Y-%m-%d')            # 固定日期
START_INDEX = 1                      # 从第几个板块开始
END_INDEX = 128                      # 到第几个板块结束

def get_config_url(bk_name):
    """
    从 config 表获取板块个股数据的接口地址。
    SQL: select value from config where name = '{bk_name}' and type = 1
    """
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        sql = "SELECT value FROM config WHERE name = %s AND type = 1"
        cursor.execute(sql, (bk_name,))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            print(f"警告：未在 config 表中找到板块 [{bk_name}] 的接口配置。")
            return None
    except Exception as e:
        print(f"查询 config 表时发生错误 ({bk_name}): {e}")
        return None
    finally:
        if conn:
            conn.close()

def save_to_mysql(data_list, bk_name):
    """
    将抓取到的板块成员个股资金流向数据存入 MySQL 数据库。
    字段映射参考 test_get_stock_inflow.py
    """
    if not data_list:
        print(f"板块 [{bk_name}] 无数据可存入。")
        return
    
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        records = []
        for i, row in enumerate(data_list):
            # 格式化金额字段：除以10000，保留2位小数，拼接“万”
            def format_je(val):
                try:
                    if val is None or val == "": return "0.00万"
                    return f"{round(float(val) / 10000, 2)}万"
                except:
                    return "0.00万"
            
            # 格式化占比字段：拼接“%”
            def format_percent(val):
                if val is None or val == "-" or val == "": return "0.00%"
                return f"{val}%"
            
            # 构造插入记录 (字段顺序需与 SQL 对应)
            record = (
                bk_name,                         # bkname: 板块名称
                str(i + 1),                      # no: 初始排名
                row.get('f12'),                  # code: 股票代码
                row.get('f14'),                  # name: 股票名称
                str(row.get('f2', '')),          # close: 最新价
                format_percent(row.get('f3')),   # zdf: 涨跌幅
                format_je(row.get('f62')),       # zl_je: 主力净流入_金额
                format_percent(row.get('f184')), # zl_jzb: 主力净流入_净占比
                format_je(row.get('f66')),       # cdd_je: 超大单净流入_金额
                format_percent(row.get('f69')),  # cdd_jzb: 超大单净流入_净占比
                format_je(row.get('f72')),       # dd_je: 大单净流入_金额
                format_percent(row.get('f75')),  # dd_jzb: 大单净流入_净占比
                format_je(row.get('f78')),       # zd_je: 中单净流入_金额
                format_percent(row.get('f81')),  # zd_jzb: 中单净流入_净占比
                format_je(row.get('f84')),       # xd_je: 小单净流入_金额
                format_percent(row.get('f87')),  # xd_jzb: 小单净流入_净占比
                FIXED_DATE                       # date: 日期
            )
            records.append(record)
        
        # 批量插入语句
        insert_sql = f"""
        INSERT INTO {TABLE_NAME} (
            `bkname`, `no`, `code`, `name`, `close`, `zdf`, 
            `zl_je`, `zl_jzb`, `cdd_je`, `cdd_jzb`, 
            `dd_je`, `dd_jzb`, `zd_je`, `zd_jzb`, 
            `xd_je`, `xd_jzb`, `date`
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(insert_sql, records)
        conn.commit()
        print(f"成功将板块 [{bk_name}] 的 {len(records)} 条成员股票数据存入 {TABLE_NAME}。")
        
    except Exception as e:
        print(f"写入 MySQL 时发生错误: {e}")
    finally:
        if conn:
            conn.close()

def fix_no_sequentially(bk_name):
    """
    每次抓取完一个板块后，修正该板块下对应日期的 no 字段顺序。
    """
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        update_sql = f"""
        UPDATE {TABLE_NAME} t
        JOIN (
            SELECT iid, ROW_NUMBER() OVER (ORDER BY iid) AS rn
            FROM {TABLE_NAME}
            WHERE date = '{FIXED_DATE}' AND bkname = '{bk_name}'
        ) AS ranked ON t.iid = ranked.iid
        SET t.no = ranked.rn
        WHERE t.date = '{FIXED_DATE}' AND t.bkname = '{bk_name}'
        """
        cursor.execute(update_sql)
        conn.commit()
        print(f"成功修正 {TABLE_NAME} 表中 [{bk_name}] 板块日期为 {FIXED_DATE} 的 no 字段顺序。")
    except Exception as e:
        print(f"修正 [{bk_name}] no 字段时发生错误: {e}")
    finally:
        if conn:
            conn.close()

def get_bk_stock():
    """
    主逻辑：抓取板块列表，获取前 N 个板块，再分别抓取其成员股票并存入数据库。
    """
    start_time = time.time()
    # 1. 获取板块列表数据
    bk_list_url = "https://data.eastmoney.com/dataapi/bkzj/getbkzj?key=f62&code=m%3A90%2Bs%3A4"
    headers_list = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
    }
    
    try:
        print(f"正在获取板块列表: {bk_list_url}")
        response = requests.get(bk_list_url, headers=headers_list)
        response.raise_for_status()
        bk_json = response.json()
        bk_diff = bk_json.get("data", {}).get("diff", [])
    except Exception as e:
        print(f"获取板块列表失败: {e}")
        return

    if not bk_diff:
        print("未获取到板块数据。")
        return

    # 根据 START_INDEX 和 END_INDEX 获取目标板块范围 (Python 切片是左闭右开)
    target_bk_list = bk_diff[START_INDEX-1 : END_INDEX]
    print(f"已获取板块列表，准备处理 第 {START_INDEX} 到 第 {END_INDEX} 个板块（共 {len(target_bk_list)} 个）...")

    # 会话与请求头初始化 (参考 test_get_stock_inflow.py)
    session = requests.Session()
    base_cookie = "qgqp_b_id=1ff899deb2754493bd78d685f931f0ea; st_nvi=L87pFwNzUoC8jmQBMymBX3765; nid18=08abed9af61161fe18a0aebc4025ba93; nid18_create_time=1775446043644; gviem=fN8QFHLXgu3RqeGuaCrV13e41; gviem_create_time=1775446043644; fullscreengg=1; fullscreengg2=1; st_si=39946881941622; st_asi=delete; wsc_checkuser_ok=1; st_pvi=28182120717568; st_sp=2026-04-06%2011%3A27%3A23; st_inirUrl=https%3A%2F%2Fcn.bing.com%2F;"
    
    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Connection': 'keep-alive',
        'Referer': 'https://data.eastmoney.com/zjlx/detail.html',
        'Sec-Fetch-Dest': 'script',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'same-site',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }

    st_sn = 1

    for idx, bk_item in enumerate(target_bk_list, start=START_INDEX):
        bk_name = bk_item.get("f14")
        if not bk_name:
            continue
            
        print(f"\n======== [第 {idx} 个] 正在抓取板块: {bk_name} ========")
        
        # 从数据库获取该板块对应的接口地址
        config_url = get_config_url(bk_name)
        if not config_url:
            continue
            
        # 分页抓取该板块成员股票
        current_bk_stocks = []
        current_page = 1
        end_page = 1
        
        while current_page <= end_page:
            # 动态生成 Cookie 相关标识
            now = datetime.now()
            timestamp_ms = int(now.timestamp() * 1000)
            timestamp_str = now.strftime('%Y%m%d%H%M%S%f')[:-3]
            st_psi = f"{timestamp_str}-113300300813-3380653124"
            headers['Cookie'] = f"{base_cookie} st_sn={st_sn}; st_psi={st_psi}"
            
            # 动态生成 cb 参数
            random_str = ''.join([str(random.randint(0, 9)) for _ in range(20)])
            cb = f"jQuery1123{random_str}_{timestamp_ms}"
            
            # 构造分页 URL
            # 替换 config_url 中的 pn 参数和 cb 参数
            target_url = config_url
            # 如果 URL 中包含 pn=1，替换为当前页；否则在末尾拼接
            if "pn=" in target_url:
                target_url = re.sub(r'pn=\d+', f'pn={current_page}', target_url)
            else:
                target_url += f"&pn={current_page}"
            
            # 替换或拼接 cb 参数
            if "cb=" in target_url:
                target_url = re.sub(r'cb=jQuery\d+_\d+', f'cb={cb}', target_url)
            else:
                target_url += f"&cb={cb}"

            print(f"抓取 [{bk_name}] 第 {current_page}/{end_page if end_page > 1 else '?'} 页...")
            
            try:
                response = session.get(target_url, headers=headers)
                response.raise_for_status()
                
                content = response.text
                json_match = re.search(r'\((.*)\)', content)
                if json_match:
                    json_data = json.loads(json_match.group(1))
                else:
                    json_data = response.json()
                    
                data = json_data.get("data", {})
                if not data:
                    print(f"板块 [{bk_name}] 第 {current_page} 页无有效数据。")
                    break
                
                # 第一页获取总页数
                if current_page == 1:
                    total_count = data.get("total", 0)
                    end_page = math.ceil(total_count / 50)
                    print(f"[{bk_name}] 成员总数: {total_count}, 总页数: {end_page}")
                
                diff = data.get("diff", [])
                if not diff:
                    break
                    
                current_bk_stocks.extend(diff)
                
                current_page += 1
                st_sn += 1
                
                if current_page <= end_page:
                    time.sleep(5)
            except Exception as e:
                print(f"抓取板块 [{bk_name}] 成员数据时发生错误: {e}")
                break
        
        # 存入数据库
        save_to_mysql(current_bk_stocks, bk_name)
        # 修正该板块的排名
        fix_no_sequentially(bk_name)
        
    duration_min = round((time.time() - start_time) / 60, 2)
    print(f"\n所有指定板块抓取任务完成，共消耗{duration_min}分钟。")

if __name__ == "__main__":
    get_bk_stock()
