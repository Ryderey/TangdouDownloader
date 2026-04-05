        return os.path.join(self.tasks_dir, f"{task_id}.json")
    
    def save(self, task: Task):
        """保存任务到文件"""
        filepath = self._get_task_file(task.id)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(task.to_dict(), f, ensure_ascii=False, indent=2)
    
    def get(self, task_id: str) -> Optional[Task]:
        """从文件读取任务"""
        filepath = self._get_task_file(task_id)
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            task = Task(
                id=data['id'],
                url=data['url'],
                skip_seconds=data.get('skip_seconds', 5),
                status=data.get('status', 'pending'),