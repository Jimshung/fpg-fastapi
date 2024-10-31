from typing import Dict, List
import traceback
import logging
from datetime import datetime

class ErrorAnalyzer:
    def __init__(self):
        self.errors: List[Dict] = []
        
    def capture_error(self, error: Exception, context: str):
        error_info = {
            'timestamp': datetime.now(),
            'type': type(error).__name__,
            'message': str(error),
            'context': context,
            'traceback': traceback.format_exc(),
            'severity': self._determine_severity(error)
        }
        self.errors.append(error_info)
        
    def generate_report(self) -> str:
        if not self.errors:
            return "✅ 無錯誤發生"
            
        report = ["🔍 錯誤分析報告:\n"]
        for error in self.errors:
            report.append(f"⚠️ {error['timestamp']}: {error['type']}")
            report.append(f"📝 描述: {error['message']}")
            report.append(f"📍 位置: {error['context']}")
            report.append(f"⚡ 嚴重度: {error['severity']}\n")
        
        return "\n".join(report)
        
    def _determine_severity(self, error: Exception) -> str:
        if isinstance(error, (ConnectionError, TimeoutError)):
            return "高"
        elif isinstance(error, ValueError):
            return "中"
        return "低" 