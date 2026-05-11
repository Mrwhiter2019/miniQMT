import os
import sys
import pandas as pd
from datetime import datetime

# 将项目根目录添加到路径中，确保能导入模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from data_manager import get_data_manager
import config

def test_export_history_data():
    """
    测试下载历史数据并导出到 CSV
    """
    # 1. 初始化数据管理器
    dm = get_data_manager()
    
    # 2. 设置参数
    stock_code = "600628.SH"
    start_date = "20260101"
    end_date = "20260511"
    export_dir = r"D:\Data"
    export_file = os.path.join(export_dir, f"{stock_code[:6]}.csv")
    
    print(f"开始下载 {stock_code} 的历史数据...")
    print(f"时间范围: {start_date} 到 {end_date}")
    
    # 3. 调用下载方法
    # 注意：download_history_data 会根据配置路由到 QMT 或 Mootdx
    df = dm.download_history_data(
        stock_code=stock_code,
        period="1d",
        start_date=start_date,
        end_date=end_date
    )
    
    if df is not None and not df.empty:
        print(f"下载成功，共 {len(df)} 条记录")
        
        # 4. 确保导出目录存在
        if not os.path.exists(export_dir):
            try:
                os.makedirs(export_dir)
                print(f"创建目录: {export_dir}")
            except Exception as e:
                print(f"创建目录失败: {e}，将尝试保存在当前目录")
                export_file = f"{stock_code[:6]}.csv"
        
        # 5. 保存为 CSV
        try:
            df.to_csv(export_file, index=False, encoding='utf-8-sig')
            print(f"数据已成功保存至: {export_file}")
            
            # 显示前几行数据
            print("\n数据预览:")
            print(df.head())
        except Exception as e:
            print(f"保存 CSV 失败: {e}")
    else:
        print("未能获取到数据，请检查 QMT 客户端是否在线或股票代码是否正确。")

if __name__ == "__main__":
    test_export_history_data()
