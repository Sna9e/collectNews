import urllib.parse
import os

try:
    import requests
except Exception:
    requests = None

def generate_and_download_chart(title, labels, values, chart_type="bar", filename="temp_chart.png"):
    """
    调用现代化 QuickChart API 生成极具设计感的商业图表
    """
    # 现代化图表配色方案 (金融投行风)
    colors = ['rgba(54, 162, 235, 0.8)', 'rgba(255, 99, 132, 0.8)', 'rgba(255, 206, 86, 0.8)', 'rgba(75, 192, 192, 0.8)']
    
    chart_config = {
        "type": chart_type,
        "data": {
            "labels": labels,
            "datasets": [{
                "label": title,
                "data": values,
                "backgroundColor": colors[:len(labels)],
                "borderWidth": 1
            }]
        },
        "options": {
            "plugins": {
                "title": {"display": True, "text": title, "font": {"size": 18}},
                "datalabels": {"display": True, "align": "end", "anchor": "end"}
            }
        }
    }
    
    import json
    # 将 JSON 配置转换为 URL 编码
    encoded_config = urllib.parse.quote(json.dumps(chart_config))
    # 拼接 API 请求地址 (高分辨率，去掉背景)
    url = f"https://quickchart.io/chart?c={encoded_config}&w=600&h=350&bkg=transparent&retina=true"
    
    if requests is None:
        return None

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            return filename
    except Exception as e:
        print(f"图表 API 调用失败: {e}")
    
    return None
