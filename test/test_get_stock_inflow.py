import requests
import time
import json
import math
import re
import pymysql
import random
from datetime import datetime

def save_to_mysql(data_list):
    """
    将抓取到的个股资金流向数据按照指定格式存入 MySQL 数据库。
    """
    if not data_list:
        print("最终未获取到任何数据，跳过数据库写入。")
        return
    
    # 配置信息
    host = '127.0.0.1'
    port = 3306
    user = 'root'
    password = 'system'
    database = 'qstock'
    now = datetime.now()
    table_name = f"stock_{now.strftime('%Y%m')}"  # 表名变量
    fixed_date = now.strftime('%Y-%m-%d')    # 日期变量
    current_page = 1
    end_page = 106 # 初始值，会被第一页请求后的 total/50 覆盖
    st_sn = 1
    
    conn = None
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        # 准备批量插入的数据
        records = []
        for i, row in enumerate(data_list):
            def format_je(val):
                try:
                    if val is None or val == "": return "0.00万"
                    return f"{round(float(val) / 10000, 2)}万"
                except:
                    return "0.00万"
            
            def format_percent(val):
                if val is None or val == "-" or val == "": return "0.00%"
                return f"{val}%"
            
            record = (
                str(i + 1),                      # no: 初始排名
                row.get('f12'),                  # code
                row.get('f14'),                  # name
                str(row.get('f2', '')),          # close
                format_percent(row.get('f3')),   # zdf
                format_je(row.get('f62')),       # zl_je
                format_percent(row.get('f184')), # zl_jzb
                format_je(row.get('f66')),       # cdd_je
                format_percent(row.get('f69')),  # cdd_jzb
                format_je(row.get('f72')),       # dd_je
                format_percent(row.get('f75')),  # dd_jzb
                format_je(row.get('f78')),       # zd_je
                format_percent(row.get('f81')),  # zd_jzb
                format_je(row.get('f84')),       # xd_je
                format_percent(row.get('f87')),  # xd_jzb
                fixed_date                       # date
            )
            records.append(record)
        
        # 1. 批量插入数据
        insert_sql = f"""
        INSERT INTO {table_name} (
            `no`, `code`, `name`, `close`, `zdf`, 
            `zl_je`, `zl_jzb`, `cdd_je`, `cdd_jzb`, 
            `dd_je`, `dd_jzb`, `zd_je`, `zd_jzb`, 
            `xd_je`, `xd_jzb`, `date`
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(insert_sql, records)
        conn.commit()
        print(f"成功将 {len(records)} 条数据插入 MySQL 数据库表 {table_name}。")
        
        # 2. 执行后续更新语句，根据 iid 重新生成连续的 no
        update_sql = f"""
        UPDATE {table_name} t
        JOIN (
            SELECT iid, ROW_NUMBER() OVER (ORDER BY iid) AS rn
            FROM {table_name}
            WHERE date = '{fixed_date}'
        ) AS ranked ON t.iid = ranked.iid
        SET t.no = ranked.rn
        WHERE t.date = '{fixed_date}'
        """
        cursor.execute(update_sql)
        conn.commit()
        print(f"成功更新 {table_name} 表中日期为 {fixed_date} 的 no 字段顺序。")
        
    except Exception as e:
        print(f"写入或更新 MySQL 时发生错误: {e}")
    finally:
        if conn:
            conn.close()

def get_stock_inflow():
    """
    循环抓取个股资金流向数据，动态生成 cb 和 Cookie，每页间隔5秒。
    """
    all_data = []
    base_cookie = "qgqp_b_id=1ff899deb2754493bd78d685f931f0ea; st_nvi=L87pFwNzUoC8jmQBMymBX3765; nid18=08abed9af61161fe18a0aebc4025ba93; nid18_create_time=1775446043644; gviem=fN8QFHLXgu3RqeGuaCrV13e41; gviem_create_time=1775446043644; fullscreengg=1; fullscreengg2=1; st_si=39946881941622; st_asi=delete; wsc_checkuser_ok=1; st_pvi=28182120717568; st_sp=2026-04-06%2011%3A27%3A23; st_inirUrl=https%3A%2F%2Fcn.bing.com%2F;"
    
    session = requests.Session()
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

    while current_page <= end_page:
        now = datetime.now()
        timestamp_ms = int(now.timestamp() * 1000)
        timestamp_str = now.strftime('%Y%m%d%H%M%S%f')[:-3]
        
        # 1. 动态生成 st_psi
        st_psi = f"{timestamp_str}-113300300813-3380653124"
        cookie_str = f"{base_cookie} st_sn={st_sn}; st_psi={st_psi}"
        headers['Cookie'] = cookie_str
        
        # 2. 动态生成 cb
        random_str = ''.join([str(random.randint(0, 9)) for _ in range(20)])
        cb = f"jQuery1123{random_str}_{timestamp_ms}"
        
        print(f"正在抓取第 {current_page}/{end_page if end_page > 1 else '?'} 页 (st_sn={st_sn})...")
        
        # 构造URL
        fs_param = "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
        url = (
            f"https://push2.eastmoney.com/api/qt/clist/get"
            f"?cb={cb}&fid=f62&po=1&pz=50&pn={current_page}&np=1&fltt=2&invt=2"
            f"&ut=8dec03ba335b81bf4ebdf7b29ec27d15"
            f"&fs={fs_param}"
            f"&fields=f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13"
        )
        
        try:
            response = session.get(url, headers=headers)
            response.raise_for_status()
            
            content = response.text
            json_match = re.search(r'\((.*)\)', content)
            if json_match:
                json_data = json.loads(json_match.group(1))
            else:
                json_data = response.json()
                
            data = json_data.get("data", {})
            if not data:
                print(f"第 {current_page} 页未获取到有效数据结构。")
                break
            
            if current_page == 1:
                total_count = data.get("total", 0)
                end_page = math.ceil(total_count / 50)
                print(f"数据总量: {total_count}, 总页数: {end_page}")
                
            diff = data.get("diff", [])
            if not diff:
                print(f"第 {current_page} 页无更多数据。")
                break
                
            all_data.extend(diff)
            print(f"已获取 {len(diff)} 条数据，累计 {len(all_data)} 条。")
            
            current_page += 1
            st_sn += 1
            
            if current_page <= end_page:
                print("等待 5 秒...")
                time.sleep(5)
                
        except Exception as e:
            print(f"抓取第 {current_page} 页时发生错误: {e}")
            if "Expecting value" in str(e):
                try:
                    print(f"原始响应内容: {response.text}")
                except:
                    pass
            break
            
    save_to_mysql(all_data)

if __name__ == "__main__":
    get_stock_inflow()
