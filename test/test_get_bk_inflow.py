import requests
import math
import time
import json
import re
import pymysql
from datetime import datetime

def save_to_mysql(data_list):
    """
    将抓取到的数据按照指定格式存入 MySQL 数据库。
    """
    if not data_list:
        print("数据为空，跳过数据库写入。")
        return
    
    # 数据库连接信息 (已更新为本地连接)
    host = '127.0.0.1'
    port = 3306
    user = 'root'
    password = 'system'
    database = 'qstock'
    now = datetime.now()
    date = now.strftime('%Y-%m-%d')
    table_name = f"bk_{now.strftime('%Y%m')}"
    current_page = 1
    total_pages = 3
    
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
            # 格式化金额字段：除以10000，保留2位小数，拼接“万”
            def format_je(val):
                try:
                    if val is None or val == "": return "0.00万"
                    return f"{round(float(val) / 10000, 2)}万"
                except:
                    return "0.00万"
            
            # 格式化占比字段：拼接“%”
            def format_percent(val):
                if val is None or val == "": return "0.00%"
                return f"{val}%"
            
            # 构造插入记录 (字段顺序需与 SQL 对应)
            record = (
                str(i + 1),                      # no: 排名，从1开始
                row.get('f14'),                  # name: 名称
                format_percent(row.get('f3')),   # zdf: 涨跌幅
                format_je(row.get('f62')),       # zl_je: 今日主力净流入_净额
                format_percent(row.get('f184')), # zl_jzb: 今日主力净流入_净占比
                format_je(row.get('f66')),       # cdd_je: 今日超大单净流入_净额
                format_percent(row.get('f69')),  # cdd_jzb: 今日超大单净流入_净占比
                format_je(row.get('f72')),       # dd_je: 今日大单净流入_净额
                format_percent(row.get('f75')),  # dd_jzb: 今日大单净流入_净占比
                format_je(row.get('f78')),       # zd_je: 今日中单净流入_净额
                format_percent(row.get('f81')),  # zd_jzb: 今日中单净流入_净占比
                format_je(row.get('f84')),       # xd_je: 今日小单净流入_净额
                format_percent(row.get('f87')),  # xd_jzb: 今日小单净流入_净占比
                date                     # date: 日期
            )
            records.append(record)
        
        # 插入语句
        sql = f"""
        INSERT INTO {table_name} (
            `no`, `name`, `zdf`, `zl_je`, `zl_jzb`, 
            `cdd_je`, `cdd_jzb`, `dd_je`, `dd_jzb`, 
            `zd_je`, `zd_jzb`, `xd_je`, `xd_jzb`, `date`
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        # 执行批量插入
        cursor.executemany(sql, records)
        conn.commit()
        print(f"成功将 {len(records)} 条数据存入 MySQL 数据库表 {table_name}。")
        
    except Exception as e:
        print(f"写入 MySQL 时发生错误: {e}")
    finally:
        if conn:
            conn.close()

def get_bk_inflow():
    """
    发送GET请求获取板块资金流向数据，并存入 MySQL 数据库。
    支持分页查询，自动抓取所有页面。
    保留原始URL中的cb参数并处理JSONP格式。
    """
    
    # 每页条数
    pz = 50
    all_diff_data = []
    
    # 原始URL中的cb参数
    cb_val = "jQuery112306531580429188594_1778900687795"
    # 基础URL，包含原始cb参数
    base_url = f"https://push2.eastmoney.com/api/qt/clist/get?cb={cb_val}&fid=f62&po=1&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A90+s%3A4&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    while current_page <= total_pages:
        # 拼接分页参数
        url = f"{base_url}&pz={pz}&pn={current_page}"
        print(f"正在请求第 {current_page}/{total_pages if total_pages > 1 else '?'} 页: {url}")
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            # 由于包含cb参数，返回的是JSONP格式，需要提取其中的JSON
            content = response.text
            json_match = re.search(r'\((.*)\)', content)
            if json_match:
                json_data = json.loads(json_match.group(1))
            else:
                json_data = response.json()
            
            data = json_data.get('data', {})
            if not data:
                print(f"第 {current_page} 页未获取到有效数据结构。")
                break
                
            # 第一页时根据total计算总页数
            if current_page == 1:
                total_count = data.get('total', 0)
                if total_count == 0:
                    print("数据总量为0，停止抓取。")
                    break
                total_pages = math.ceil(total_count / pz)
                print(f"数据总量: {total_count}, 总页数: {total_pages}")
                
            diff_data = data.get('diff', [])
            if not diff_data:
                print(f"第 {current_page} 页无更多数据内容。")
                break
                
            all_diff_data.extend(diff_data)
            
            # 页码递增
            current_page += 1
            
            # 适当延时，避免请求过于频繁
            if current_page <= total_pages:
                time.sleep(0.5)
                
        except Exception as e:
            print(f"请求第 {current_page} 页时发生错误: {e}")
            break
            
    if not all_diff_data:
        print("未获取到任何有效数据。")
        return
        
    # 存入 MySQL 数据库
    save_to_mysql(all_diff_data)

if __name__ == "__main__":
    get_bk_inflow()
