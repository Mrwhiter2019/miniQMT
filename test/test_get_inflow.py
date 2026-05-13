import requests
import pandas as pd
import os

def get_bk_inflow():
    """
    发送GET请求获取板块资金流向数据，并保存到本地Excel文件。
    """
    url = "https://data.eastmoney.com/dataapi/bkzj/getbkzj?key=f62&code=m%3A90%2Bs%3A4"
    
    print(f"正在请求数据: {url}")
    
    try:
        # 发送请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # 解析JSON
        json_data = response.json()
        
        # 获取data中的diff数据
        diff_data = json_data.get('data', {}).get('diff', [])
        
        if not diff_data:
            print("未获取到有效数据。")
            return
            
        # 转换为DataFrame
        df = pd.DataFrame(diff_data)
        
        # 字段映射说明 (可选，供参考):
        # f12: 板块代码
        # f14: 板块名称
        # f62: 今日主力净流入
        
        # 目标保存路径
        output_dir = r"D:\Data"
        output_file = os.path.join(output_dir, "bk_inflow.xlsx")
        
        # 确保目录存在
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"创建目录: {output_dir}")
            
        # 保存为Excel
        df.to_excel(output_file, index=False)
        print(f"数据已成功保存至: {output_file}")
        
    except Exception as e:
        print(f"执行过程中发生错误: {e}")

if __name__ == "__main__":
    get_bk_inflow()
