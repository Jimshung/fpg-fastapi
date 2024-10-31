from pydantic import BaseModel
from datetime import datetime
from typing import Dict, List, Optional
import json
from pathlib import Path

class PerformanceMetrics(BaseModel):
    login_duration: float
    search_duration: float
    total_duration: float
    memory_usage: float
    cpu_usage: float
    network_requests: int
    page_load_time: float

class ExecutionMetrics(BaseModel):
    start_time: datetime
    end_time: datetime
    status: str
    search_results_count: int
    errors: List[str]
    performance: PerformanceMetrics
    browser_logs: List[str]

    def save(self, base_dir: str = "app/metrics"):
        """儲存指標到 JSON 檔案"""
        Path(base_dir).mkdir(parents=True, exist_ok=True)
        
        filename = f"{self.start_time.strftime('%Y%m%d_%H%M%S')}_metrics.json"
        file_path = Path(base_dir) / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.dict(), f, default=str, ensure_ascii=False, indent=2)
        
        return file_path