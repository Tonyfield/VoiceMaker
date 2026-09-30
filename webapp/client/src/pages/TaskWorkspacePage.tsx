import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, Empty, Spin } from "antd";
import { getTask, type Task } from "../api/client";
import TaskDetail from "../components/TaskDetail";
import { getErrorMessage } from "../lib/errors";
import { useI18n } from "../i18n";

/** 全屏任务工作区：/tasks/:id。按 id 拉取任务后复用 TaskDetail 页面。 */
export default function TaskWorkspacePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const taskId = Number(id);
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(taskId)) {
      setError(t("task.empty"));
      return;
    }
    getTask(taskId)
      .then(setTask)
      .catch((e) => setError(getErrorMessage(e, t("error.request"))));
  }, [taskId, t]);

  if (error) {
    return (
      <Empty description={error} style={{ padding: 48 }}>
        <Button onClick={() => navigate("/tasks")}>{t("act.back")}</Button>
      </Empty>
    );
  }
  if (!task) {
    return (
      <div style={{ textAlign: "center", padding: 48 }}>
        <Spin />
      </div>
    );
  }

  return (
    <TaskDetail
      taskId={task.id}
      taskName={task.name}
      skipTts={task.skip_tts}
      onClose={() => navigate("/tasks")}
    />
  );
}
