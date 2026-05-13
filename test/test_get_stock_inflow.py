import requests
import pandas as pd
import time
import os
import json

def get_stock_inflow():
    """
    循环抓取个股资金流向数据（共106页），每页间隔10秒，最后保存为Excel。
    """
    all_data = []
    
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Encoding': 'gzip',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Connection': 'keep-alive',
        'Cookie': 'qgqp_b_id=1ff899deb2754493bd78d685f931f0ea; st_nvi=L87pFwNzUoC8jmQBMymBX3765; nid18=08abed9af61161fe18a0aebc4025ba93; nid18_create_time=1775446043644; gviem=fN8QFHLXgu3RqeGuaCrV13e41; gviem_create_time=1775446043644; fullscreengg=1; fullscreengg2=1; st_si=86047664715744; st_asi=delete; st_pvi=28182120717568; st_sp=2026-04-06%2011%3A27%3A23; st_inirUrl=https%3A%2F%2Fcn.bing.com%2F; st_sn=6; st_psi=2026051321475328-113300300820-7739713793',
        'Host': 'push2.eastmoney.com',
        'Referer': 'https://data.eastmoney.com/zjlx/detail.html',
        'Sec-Fetch-Dest': 'script',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'same-site',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }

    output_dir = r"D:\Data"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建目录: {output_dir}")

    start_page = 1
    end_page = 106

    for pn in range(start_page, end_page + 1):
        print(f"正在抓取第 {pn}/{end_page} 页...")
        
        # 使用用户提供的原始URL并替换pn参数
        url = f"https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery112308515507929917618_1778680067958&fid=f62&po=1&pz=50&pn={pn}&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A0%2Bt%3A6%2Bf%3A!2%2Cm%3A0%2Bt%3A13%2Bf%3A!2%2Cm%3A0%2Bt%3A80%2Bf%3A!2%2Cm%3A1%2Bt%3A2%2Bf%3A!2%2Cm%3A1%2Bt%3A23%2Bf%3A!2%2Cm%3A0%2Bt%3A7%2Bf%3A!2%2Cm%3A1%2Bt%3A3%2Bf%3A!2&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13"
        
        try:
            # 发送GET请求
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            # 由于带有cb参数，返回的是JSONP格式: jQuery1123...({...});
            content = response.text
            print(f"第 {pn} 页返回数据，{content}")
            # 提取括号中的JSON内容
            json_str = content[content.find("(")+1 : content.rfind(")")]
            json_data = json.loads(json_str)
            diff = json_data.get("data", {}).get("diff", [])
            
            if not diff:
                print(f"第 {pn} 页未获取到数据，抓取结束。")
                break
                
            all_data.extend(diff)
            print(f"已获取 {len(diff)} 条数据，累计 {len(all_data)} 条。")
            
            # 如果不是最后一页，则等待10秒
            if pn < end_page:
                print("等待 10 秒...")
                time.sleep(10)
                
        except Exception as e:
            print(f"抓取第 {pn} 页时发生错误: {e}")
            # 发生错误时可以选择继续或退出，这里选择重试或跳过？为了安全，先停止。
            break
            
    if all_data:
        # 将所有数据存入DataFrame
        df = pd.DataFrame(all_data)
        
        # 目标文件路径
        output_file = os.path.join(output_dir, "stock_inflow.xlsx")
        
        # 保存为Excel
        df.to_excel(output_file, index=False)
        print(f"--- 抓取完成 ---")
        print(f"总计获取数据: {len(all_data)} 条")
        print(f"数据已保存至: {output_file}")
    else:
        print("最终未获取到任何数据。")

if __name__ == "__main__":
    get_stock_inflow()
