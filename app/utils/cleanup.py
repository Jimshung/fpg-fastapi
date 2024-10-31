import os
import shutil
from datetime import datetime, timedelta
import logging

class CleanupService:
    def __init__(self, base_dir: str, retention_days: int = 7):
        self.base_dir = base_dir
        self.retention_days = retention_days
        self.logger = logging.getLogger(__name__)
        
        # 確保目錄存在
        os.makedirs(base_dir, exist_ok=True)
    
    async def cleanup_old_files(self):
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        cleaned_files = 0
        cleaned_size = 0
        
        self.logger.info(f"檢查 {self.base_dir} 中的檔案")
        
        # 先檢查目錄是否為空
        if not any(os.scandir(self.base_dir)):
            self.logger.info(f"目錄 {self.base_dir} 為空，無需清理")
            return {
                "files_cleaned": 0,
                "space_freed": 0,
                "message": "目錄為空，無需清理"
            }
        
        for root, dirs, files in os.walk(self.base_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if self._should_delete(file_path, cutoff_date):
                    size = os.path.getsize(file_path)
                    self.logger.info(f"清理檔案: {file_path}")
                    os.remove(file_path)
                    cleaned_files += 1
                    cleaned_size += size
        
        if cleaned_files > 0:
            cleanup_info = f"清理完成: 刪除 {cleaned_files} 個檔案，釋放 {cleaned_size/1024/1024:.2f} MB 空間"
            self.logger.info(cleanup_info)
            return {
                "files_cleaned": cleaned_files,
                "space_freed": cleaned_size,
                "message": cleanup_info
            }
        else:
            self.logger.info("沒有需要清理的檔案")
            return {
                "files_cleaned": 0,
                "space_freed": 0,
                "message": "沒有需要清理的檔案"
            }
    
    def _should_delete(self, file_path: str, cutoff_date: datetime) -> bool:
        # 檢查檔案修改時間
        mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
        return mtime < cutoff_date 