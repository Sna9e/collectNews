import json
import urllib.request
from typing import Dict

class GistMemoryManager:
    def __init__(self, github_token: str, gist_id: str):
        self.token = github_token
        self.gist_id = gist_id
        self.memory_db = {}
        self.filename = "history_bank.json"

    def load_memory(self) -> Dict:
        if not self.token or not self.gist_id:
            return {}
        try:
            url = f"https://api.github.com/gists/{self.gist_id}"
            req = urllib.request.Request(url, headers={
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {self.token}"
            })
            response = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
            gist_data = json.loads(response)
            files = gist_data.get("files", {})
            if self.filename in files:
                content = files[self.filename]["content"]
                self.memory_db = json.loads(content)
            return self.memory_db
        except Exception as e:
            print(f"☁️ 读取记忆库失败: {e}")
            return {}

    def save_memory(self):
        if not self.token or not self.gist_id or not self.memory_db:
            return
        try:
            url = f"https://api.github.com/gists/{self.gist_id}"
            content_str = json.dumps(self.memory_db, ensure_ascii=False, indent=2)
            payload = {"files": {self.filename: {"content": content_str}}}
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, method="PATCH", headers={
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {self.token}",
                "Content-Type": "application/json"
            })
            urllib.request.urlopen(req, timeout=10)
            print("☁️ 记忆库同步云端成功！")
        except Exception as e:
            print(f"☁️ 写入记忆库失败: {e}")

    def get_topic_history(self, topic: str) -> str:
        history = self.memory_db.get(topic, [])
        if not history: return "（该主题暂无历史记忆）"
        lines = [f"[{item['date']}] {item['insight']}" for item in history]
        return "\n".join(lines)

    def add_topic_memory(self, topic: str, date: str, insight: str):
        if not insight or len(insight) < 5: return
        if topic not in self.memory_db: self.memory_db[topic] = []
        
        # 避免同一天重复记录
        for item in self.memory_db[topic]:
            if item['date'] == date:
                item['insight'] = insight
                return
                
        self.memory_db[topic].append({"date": date, "insight": insight})
        # 工业级防御：只保留最近 5 条记忆，防止 Token 撑爆
        self.memory_db[topic] = self.memory_db[topic][-5:]
