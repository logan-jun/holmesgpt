"""Tests for TodoListMiddleware."""

import pytest

from holmes.core.langchain.todo_middleware import TodoListMiddleware


class TestTodoListMiddleware:
    def setup_method(self):
        self.mw = TodoListMiddleware()

    def test_initial_state(self):
        assert self.mw.tasks == []
        assert self.mw.all_tasks_completed()
        assert not self.mw.should_force_continue()
        assert self.mw.get_task_status_injection() is None

    def test_update_tasks_pending(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "pending"},
            {"id": "2", "content": "Check logs", "status": "pending"},
        ])
        assert len(self.mw.tasks) == 2
        assert not self.mw.all_tasks_completed()

    def test_update_tasks_mixed_status(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "completed"},
            {"id": "2", "content": "Check logs", "status": "pending"},
        ])
        assert not self.mw.all_tasks_completed()

    def test_all_tasks_completed(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "completed"},
            {"id": "2", "content": "Check logs", "status": "completed"},
        ])
        assert self.mw.all_tasks_completed()

    def test_all_tasks_completed_with_failed(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "completed"},
            {"id": "2", "content": "Check logs", "status": "failed"},
        ])
        assert self.mw.all_tasks_completed()

    def test_should_force_continue_with_pending(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "pending"},
        ])
        assert self.mw.should_force_continue()

    def test_should_force_continue_limit(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "pending"},
        ])
        # Exhaust force continue limit
        for _ in range(5):
            assert self.mw.should_force_continue()

        # After limit, should return False
        assert not self.mw.should_force_continue()

    def test_force_continue_not_triggered_when_complete(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "completed"},
        ])
        assert not self.mw.should_force_continue()

    def test_task_status_injection(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "pending"},
        ])
        injection = self.mw.get_task_status_injection()
        assert injection is not None
        assert "Check pods" in injection

    def test_force_continue_message(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "pending"},
            {"id": "2", "content": "Check logs", "status": "completed"},
        ])
        msg = self.mw.get_force_continue_message()
        assert "1 incomplete" in msg
        assert "Check pods" in msg
        assert "Check logs" not in msg  # completed task should not appear

    def test_get_metrics(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "pending"},
        ])
        self.mw.should_force_continue()  # Trigger one force continue
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "completed"},
        ])

        metrics = self.mw.get_metrics()
        assert metrics["total_task_updates"] == 2
        assert metrics["forced_continues"] == 1
        assert metrics["completed_tasks"] == 1
        assert metrics["pending_tasks"] == 0

    def test_reset(self):
        self.mw.update_tasks([
            {"id": "1", "content": "Check pods", "status": "pending"},
        ])
        self.mw.should_force_continue()
        self.mw.reset()

        assert self.mw.tasks == []
        assert self.mw.all_tasks_completed()
        assert self.mw.get_task_status_injection() is None
        metrics = self.mw.get_metrics()
        assert metrics["total_task_updates"] == 0
        assert metrics["forced_continues"] == 0
