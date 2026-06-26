import os
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from conf_t.models import Lesson, Task, SessionStats

def validate_input(user_input: str, task: Task, platform: str) -> bool:
    """
    Validates the user's input command against the task's expected regex and aliases.
    Applies case-sensitivity based on the platform:
    - Cisco, PowerShell: case-insensitive
    - Linux, Git, Docker: case-sensitive
    """
    cleaned_input = user_input.strip()
    
    # Determine regex flags
    is_case_insensitive = platform.lower() in ["cisco", "powershell"]
    flags = re.IGNORECASE if is_case_insensitive else 0

    # 1. Test against expected regex pattern
    try:
        pattern = re.compile(task.expected, flags)
        if pattern.match(cleaned_input):
            return True
    except re.error:
        # Fallback to exact match if regex compilation fails
        pass

    # 2. Test against aliases list
    for alias in task.aliases:
        alias_clean = alias.strip()
        if is_case_insensitive:
            if cleaned_input.lower() == alias_clean.lower():
                return True
        else:
            if cleaned_input == alias_clean:
                return True

    return False


class LessonLoader:
    """Loads and caches lessons from JSON files in the lessons directory."""
    def __init__(self, lessons_dir: Optional[Path] = None):
        if lessons_dir is None:
            # Default to the lessons subdirectory inside the package
            self.lessons_dir = Path(__file__).parent / "lessons"
        else:
            self.lessons_dir = Path(lessons_dir)

    def load_all_lessons(self) -> List[Lesson]:
        lessons = []
        if not self.lessons_dir.exists() or not self.lessons_dir.is_dir():
            return lessons

        for file_path in self.lessons_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    lessons.append(Lesson.from_dict(data))
            except (json.JSONDecodeError, KeyError, OSError):
                # Fail silently or ignore malformed lesson files to avoid crash
                continue
        return lessons

    def get_lesson_by_id(self, lesson_id: str) -> Optional[Lesson]:
        lessons = self.load_all_lessons()
        for lesson in lessons:
            if lesson.id == lesson_id:
                return lesson
        return None

    def save_lesson(self, lesson: Lesson) -> bool:
        """Saves a Lesson object as a JSON file in the lessons directory."""
        if not self.lessons_dir.exists():
            try:
                self.lessons_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                return False
        
        file_path = self.lessons_dir / f"{lesson.id}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(lesson.to_dict(), f, indent=4)
            return True
        except OSError:
            return False


class ProgressManager:
    """Manages reading and writing user progress stats to a JSON file."""
    def __init__(self, filepath: Optional[Path] = None):
        if filepath is None:
            self.filepath = Path.home() / ".conf_t_progress.json"
        else:
            self.filepath = Path(filepath)
        self.data = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        if not self.filepath.exists():
            return self._default_structure()
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure all default keys exist
                defaults = self._default_structure()
                for k, v in defaults.items():
                    if k not in data:
                        data[k] = v
                return data
        except (json.JSONDecodeError, OSError):
            return self._default_structure()

    def _default_structure(self) -> Dict[str, Any]:
        return {
            "completed_lessons": [],      # List of lesson IDs completed
            "failed_tasks": [],           # List of task definitions for spaced review/re-queueing
            "total_attempts": 0,
            "correct_first_try": 0,
            "skipped_count": 0,
            "platform_stats": {}          # e.g., {"Cisco": {"attempts": 10, "correct": 8}}
        }

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
        except OSError:
            pass  # Fail silently if directory or permissions block writes

    def record_attempt(self, lesson_id: str, platform: str, task_id: str, is_correct: bool, is_first_try: bool, is_skipped: bool):
        self.data["total_attempts"] += 1
        
        # Initialize platform stats
        if platform not in self.data["platform_stats"]:
            self.data["platform_stats"][platform] = {
                "attempts": 0,
                "correct_first_try": 0,
                "skipped": 0
            }
            
        p_stats = self.data["platform_stats"][platform]
        p_stats["attempts"] += 1

        if is_skipped:
            self.data["skipped_count"] += 1
            p_stats["skipped"] += 1
            # Add to failed tasks queue so they can review it
            self.add_failed_task(lesson_id, task_id)
        elif is_correct:
            if is_first_try:
                self.data["correct_first_try"] += 1
                p_stats["correct_first_try"] += 1
            # Remove from failed tasks queue if they got it correct
            self.remove_failed_task(task_id)
        else:
            # Incorrect attempt, add to failed tasks queue
            self.add_failed_task(lesson_id, task_id)
            
        self.save()

    def add_failed_task(self, lesson_id: str, task_id: str):
        # Format stored as a dictionary to easily identify the lesson
        entry = {"lesson_id": lesson_id, "task_id": task_id}
        if entry not in self.data["failed_tasks"]:
            self.data["failed_tasks"].append(entry)

    def remove_failed_task(self, task_id: str):
        self.data["failed_tasks"] = [
            item for item in self.data["failed_tasks"] if item["task_id"] != task_id
        ]

    def mark_lesson_completed(self, lesson_id: str):
        if lesson_id not in self.data["completed_lessons"]:
            self.data["completed_lessons"].append(lesson_id)
            self.save()

    def get_failed_task_entries(self) -> List[Dict[str, str]]:
        return self.data.get("failed_tasks", [])

    def reset_progress(self):
        self.data = self._default_structure()
        self.save()
