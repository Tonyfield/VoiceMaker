import { ensureDirs, PORT } from "./config";
import { createApp } from "./app";
import { initDatabase } from "./db/database";
import { logger } from "./logger";
import { taskService } from "./services/taskService";

ensureDirs();
initDatabase();
taskService.recoverInterruptedTasks();
// 一次性迁移：旧命名 audio-<key>.<ext> → <key>-<内容hash>.<ext>（幂等，迁移后无旧文件）。
taskService.migrateAllLegacyAudioNames();

const app = createApp();
app.listen(PORT, () => {
  logger.success(`🚀 VoiceCloner Web 服务已启动: http://localhost:${PORT}`);
});