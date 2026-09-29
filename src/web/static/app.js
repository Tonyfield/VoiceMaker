const state = {
  pollInterval: 3000,
  networkFailures: 0,
  activeTab: "tasks",
  models: [],
  modelMap: new Map(),
  tasks: [],
  selectedTaskId: null,
  selectedTaskDetail: null,
  artifacts: [],
  selectedArtifacts: new Set(),
  voiceProfiles: [],
  selectedProfileName: null,
  pendingVoiceAsset: null,
  drawerWidth: Math.round(window.innerWidth * 0.5),
  tooltipTimer: null,
  tooltipTarget: null,
  pointerX: 0,
  pointerY: 0,
  confirmResolver: null,
  activeDrawerTab: "status",
  taskDetailRequestVersion: 0,
  uiEvents: [],
  pendingAlertEvents: [],
  activeAlertEvent: null,
  connectionWarningActive: false,
};

const EVENT_STORAGE_KEY = "voicecloner-ui-events-v1";
const MAX_CACHED_UI_EVENTS = 120;

const LANGUAGE_LABELS = {
  auto: "自动检测",
  "zh-cn": "中文",
  en: "英文",
  ja: "日语",
  ko: "韩语",
  de: "德语",
  fr: "法语",
  ru: "俄语",
  pt: "葡萄牙语",
  es: "西班牙语",
  it: "意大利语",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function createId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `event-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function normalizeEventMessage(value) {
  const message = value instanceof Error ? value.message : String(value ?? "").trim();
  if (!message) {
    return "发生未知异常，请稍后重试。";
  }
  if (message.includes("Failed to fetch")) {
    return "网络请求失败，请检查服务连接状态。";
  }
  return message;
}

function buildHttpError(response, payload) {
  const error = new Error(payload.detail || response.statusText || `HTTP ${response.status}`);
  error.status = response.status;
  error.url = response.url;
  return error;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw buildHttpError(response, payload);
  }
  return response.json();
}

async function requestBlob(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw buildHttpError(response, payload);
  }
  return response.blob();
}

function $(id) {
  return document.getElementById(id);
}

function setConnectionState(connected, message) {
  const badge = $("connectionBadge");
  badge.textContent = message;
  badge.className = connected ? "badge badge-live" : "badge badge-error";
}

function formatAppHeading(appMeta) {
  const name = String(appMeta?.name || "VoiceCloner").trim();
  const version = String(appMeta?.version || "").trim();
  return version ? `${name} v${version}` : name;
}

function renderAppHeading(appMeta) {
  const heading = formatAppHeading(appMeta);
  const titleNode = $("appTitle");
  if (titleNode) {
    titleNode.textContent = heading;
  }
  document.title = heading;
}

function formatBytes(value) {
  if (!value) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function updateDrawerWidth(value) {
  const minWidth = window.innerWidth / 3;
  const maxWidth = window.innerWidth * 0.875;
  state.drawerWidth = Math.max(minWidth, Math.min(maxWidth, value));
  document.documentElement.style.setProperty("--drawer-width", `${state.drawerWidth}px`);
}

function selectedModel() {
  const select = $("modelName");
  return state.modelMap.get(select.value) || null;
}

function selectedProfile() {
  return state.voiceProfiles.find((item) => item.name === state.selectedProfileName) || null;
}

function selectedModelProfile() {
  return selectedModel()?.profile || {};
}

function taskInputId(name) {
  return `taskInput-${name}`;
}

function languageLabel(value) {
  return LANGUAGE_LABELS[value] || value;
}

function pathTail(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  const parts = raw.split(/[\\/]/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : raw;
}

function formatTaskValue(value, defaultValue = "未设置") {
  if (value === null || value === undefined || value === "") {
    return defaultValue;
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (Array.isArray(value)) {
    const values = value.map((item) => formatTaskValue(item, "")).filter(Boolean);
    return values.length ? values.join(" / ") : defaultValue;
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function inputModeLabel(model) {
  const profile = model?.profile || {};
  const inputs = profile.task_inputs || [];
  if (model?.requires_reference) {
    return inputs.some((field) => field.name === "x_vector_only_mode") ? "参考音频克隆" : "参考音频驱动";
  }
  if (inputs.some((field) => field.name === "speaker")) {
    return "预设音色";
  }
  if (profile.supports_voice_instruction) {
    return "描述生成";
  }
  return "标准文本合成";
}

function renderTaskReferenceSection(model) {
  const section = $("taskReferenceSection");
  const hint = $("taskReferenceHint");
  const voiceFile = $("voiceFile");
  const voiceProfile = $("voiceProfile");
  if (!model || !model.requires_reference) {
    section.classList.add("hidden");
    voiceFile.disabled = true;
    voiceProfile.disabled = true;
    voiceFile.value = "";
    voiceProfile.value = "";
    hint.textContent = "";
    return;
  }

  const profile = model.profile || {};
  section.classList.remove("hidden");
  voiceFile.disabled = false;
  voiceProfile.disabled = false;
  hint.textContent = profile.min_reference_audio_seconds
    ? `该模型需要参考音频，可直接上传文件或选择已保存语音配置。建议参考音频不少于 ${profile.min_reference_audio_seconds} 秒。`
    : "该模型需要参考音频，可直接上传文件或选择已保存语音配置。";
}

function renderDynamicTaskInputs(model) {
  const container = $("taskModelInputs");
  const profile = model?.profile || {};
  const inputs = profile.task_inputs || [];
  if (!inputs.length) {
    container.innerHTML = '<p class="field-summary">当前模型没有额外任务参数。</p>';
    return;
  }

  container.innerHTML = inputs
    .map((field) => {
      const fieldId = taskInputId(field.name);
      const required = field.required ? "required" : "";
      const help = field.help ? `<p class="field-help">${escapeHtml(field.help)}</p>` : "";
      if (field.type === "textarea") {
        return `
          <label>
            <span>${escapeHtml(field.label || field.name)}</span>
            <textarea id="${escapeHtml(fieldId)}" name="${escapeHtml(field.name)}" rows="${Number(field.rows || 3)}" placeholder="${escapeHtml(field.placeholder || "")}" ${required}>${escapeHtml(field.default || "")}</textarea>
            ${help}
          </label>
        `;
      }
      if (field.type === "select") {
        const options = (field.options || [])
          .map((option) => {
            const selected = String(option.value) === String(field.default || "") ? "selected" : "";
            return `<option value="${escapeHtml(option.value)}" ${selected}>${escapeHtml(option.label || option.value)}</option>`;
          })
          .join("");
        return `
          <label>
            <span>${escapeHtml(field.label || field.name)}</span>
            <select id="${escapeHtml(fieldId)}" name="${escapeHtml(field.name)}" ${required}>${options}</select>
            ${help}
          </label>
        `;
      }
      if (field.type === "checkbox") {
        return `
          <label class="checkbox-field">
            <input id="${escapeHtml(fieldId)}" name="${escapeHtml(field.name)}" type="checkbox" ${field.default ? "checked" : ""}>
            <span class="checkbox-copy">
              <strong>${escapeHtml(field.label || field.name)}</strong>
              ${help}
            </span>
          </label>
        `;
      }
      if (field.type === "number") {
        const min = field.min !== undefined ? `min="${escapeHtml(String(field.min))}"` : "";
        const max = field.max !== undefined ? `max="${escapeHtml(String(field.max))}"` : "";
        const step = field.step !== undefined ? `step="${escapeHtml(String(field.step))}"` : "";
        return `
          <label>
            <span>${escapeHtml(field.label || field.name)}</span>
            <input id="${escapeHtml(fieldId)}" name="${escapeHtml(field.name)}" type="number" value="${escapeHtml(field.default || "")}" placeholder="${escapeHtml(field.placeholder || "")}" ${min} ${max} ${step} ${required}>
            ${help}
          </label>
        `;
      }
      return `
        <label>
          <span>${escapeHtml(field.label || field.name)}</span>
          <input id="${escapeHtml(fieldId)}" name="${escapeHtml(field.name)}" type="text" value="${escapeHtml(field.default || "")}" placeholder="${escapeHtml(field.placeholder || "")}" ${required}>
          ${help}
        </label>
      `;
    })
    .join("");
}

function syncLanguageOptions(model) {
  const select = $("language");
  const current = select.value;
  const supported = model?.profile?.supported_languages?.length
    ? model.profile.supported_languages
    : ["auto", "zh-cn", "en", "ja", "ko"];
  select.innerHTML = supported
    .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(languageLabel(value))}</option>`)
    .join("");
  if (supported.includes(current)) {
    select.value = current;
  } else if (supported.includes("auto")) {
    select.value = "auto";
  } else {
    select.value = supported[0] || "auto";
  }
}

function renderTaskForm() {
  const model = selectedModel();
  renderTaskReferenceSection(model);
  renderDynamicTaskInputs(model);
  syncLanguageOptions(model);
  renderModelProfileHint();
}

function setText(id, value) {
  $(id).textContent = value;
}

function setFormMessage(id, message = "", isError = true) {
  const element = $(id);
  element.textContent = message;
  element.style.color = isError ? "var(--danger)" : "var(--success)";
}

function persistUiEvents() {
  try {
    window.localStorage?.setItem(EVENT_STORAGE_KEY, JSON.stringify(state.uiEvents));
  } catch (error) {
    console.warn("Failed to persist UI events", error);
  }
}

function renderEventCenter() {
  const count = state.uiEvents.length;
  const countBadge = $("eventCountBadge");
  const eventLogMeta = $("eventLogMeta");
  const clearButton = $("clearEventsButton");
  const eventList = $("eventList");

  if (countBadge) {
    countBadge.textContent = count > 99 ? "99+" : String(count);
    countBadge.classList.toggle("hidden", count === 0);
  }

  if (eventLogMeta) {
    eventLogMeta.textContent = count
      ? `已缓存 ${count} 条事件，按发生顺序记录。`
      : "当前没有错误或告警事件。";
  }

  if (clearButton) {
    clearButton.disabled = count === 0;
  }

  if (!eventList) {
    return;
  }

  if (count === 0) {
    eventList.innerHTML = '<div class="empty-state">当前没有错误或告警事件。</div>';
    return;
  }

  eventList.innerHTML = state.uiEvents
    .map(
      (item) => `
        <article class="event-item event-item--${escapeHtml(item.level)}" data-event-id="${escapeHtml(item.id)}">
          <div class="event-item-head">
            <div class="event-item-title-block">
              <div class="event-item-meta">
                <span class="event-level-badge event-level-badge--${escapeHtml(item.level)}">${item.level === "warning" ? "告警" : "错误"}</span>
                <span>${escapeHtml(item.source || "界面")}</span>
                <span>${escapeHtml(formatDate(item.createdAt))}</span>
              </div>
              <h3 class="event-item-title">${escapeHtml(item.title || "未命名事件")}</h3>
            </div>
            <button class="event-delete-button" type="button" data-delete-event-id="${escapeHtml(item.id)}" data-tooltip="删除这条事件记录">删除</button>
          </div>
          <p class="event-item-message">${escapeHtml(item.message || "")}</p>
        </article>
      `
    )
    .join("");
}

function loadCachedUiEvents() {
  try {
    const rawValue = window.localStorage?.getItem(EVENT_STORAGE_KEY);
    if (!rawValue) {
      state.uiEvents = [];
      renderEventCenter();
      return;
    }
    const parsed = JSON.parse(rawValue);
    state.uiEvents = Array.isArray(parsed)
      ? parsed
          .filter((item) => item && typeof item === "object")
          .map((item) => ({
            id: String(item.id || createId()),
            level: item.level === "warning" ? "warning" : "error",
            title: String(item.title || "未命名事件"),
            message: normalizeEventMessage(item.message),
            source: String(item.source || "界面"),
            createdAt: String(item.createdAt || new Date().toISOString()),
          }))
          .slice(-MAX_CACHED_UI_EVENTS)
      : [];
  } catch (error) {
    state.uiEvents = [];
    console.warn("Failed to restore cached UI events", error);
  }
  renderEventCenter();
}

function openEventLogModal() {
  renderEventCenter();
  openModal("eventLogModal");
}

function deleteUiEvent(eventId) {
  state.uiEvents = state.uiEvents.filter((item) => item.id !== eventId);
  persistUiEvents();
  renderEventCenter();
}

function clearUiEvents() {
  state.uiEvents = [];
  persistUiEvents();
  renderEventCenter();
}

function showNextEventAlert() {
  if (state.activeAlertEvent || state.pendingAlertEvents.length === 0) {
    return;
  }

  const eventItem = state.pendingAlertEvents.shift();
  state.activeAlertEvent = eventItem;
  const levelLabel = eventItem.level === "warning" ? "告警" : "错误";

  $("eventAlertCard").dataset.level = eventItem.level;
  $("eventAlertKicker").textContent = eventItem.level === "warning" ? "Warning" : "Error";
  $("eventAlertTitle").textContent = eventItem.title;
  $("eventAlertLevelBadge").textContent = levelLabel;
  $("eventAlertLevelBadge").className = `event-level-badge event-level-badge--${eventItem.level}`;
  $("eventAlertSource").textContent = `${eventItem.source} · ${formatDate(eventItem.createdAt)}`;
  $("eventAlertMessage").textContent = eventItem.message;
  $("eventAlertCloseButton").textContent = eventItem.level === "warning" ? "继续查看" : "知道了";
  openModal("eventAlertModal");
}

function closeEventAlertDialog(options = {}) {
  const openList = Boolean(options.openList);
  if (!state.activeAlertEvent) {
    closeModal("eventAlertModal");
    if (openList) {
      openEventLogModal();
    }
    return;
  }

  state.activeAlertEvent = null;
  closeModal("eventAlertModal");
  if (openList) {
    openEventLogModal();
  }
  window.setTimeout(showNextEventAlert, 0);
}

function inferEventLevel(error, fallbackLevel = "error") {
  if (fallbackLevel === "warning") {
    return "warning";
  }
  const status = Number(error?.status || 0);
  return status === 503 ? "warning" : "error";
}

function pushUiEvent({ level = "error", title, message, source = "界面", showDialog = true }) {
  const eventItem = {
    id: createId(),
    level: level === "warning" ? "warning" : "error",
    title: String(title || (level === "warning" ? "告警" : "错误")),
    message: normalizeEventMessage(message),
    source: String(source || "界面"),
    createdAt: new Date().toISOString(),
  };

  state.uiEvents = [...state.uiEvents, eventItem].slice(-MAX_CACHED_UI_EVENTS);
  persistUiEvents();
  renderEventCenter();

  if (showDialog) {
    state.pendingAlertEvents.push(eventItem);
    showNextEventAlert();
  }

  return eventItem;
}

function reportUiError(error, options = {}) {
  const {
    title = "操作失败",
    source = "界面",
    formMessageId = "",
    fallbackLevel = "error",
    showDialog = true,
  } = options;
  const message = normalizeEventMessage(error);
  if (formMessageId) {
    setFormMessage(formMessageId, message, true);
  }
  return pushUiEvent({
    level: inferEventLevel(error, fallbackLevel),
    title,
    message,
    source,
    showDialog,
  });
}

function reportUiWarning(message, options = {}) {
  const { title = "告警", source = "界面", showDialog = true } = options;
  return pushUiEvent({ level: "warning", title, message, source, showDialog });
}

function reportConnectionWarning(error, source) {
  if (state.connectionWarningActive) {
    return;
  }
  state.connectionWarningActive = true;
  const detail = normalizeEventMessage(error);
  const suffix = detail && detail !== "网络请求失败，请检查服务连接状态。" ? ` 详情：${detail}` : "";
  reportUiWarning(`与后台通信失败，界面会自动重试。${suffix}`, {
    title: "连接告警",
    source,
  });
}

function clearConnectionWarning() {
  state.connectionWarningActive = false;
}

function attachGlobalErrorHandlers() {
  window.addEventListener("error", (event) => {
    reportUiError(event.error || new Error(event.message || "前端运行时异常"), {
      title: "前端运行异常",
      source: "浏览器运行时",
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    reportUiError(event.reason || new Error("未处理的异步异常"), {
      title: "异步操作失败",
      source: "浏览器 Promise",
    });
  });
}

function openModal(id) {
  $(id).classList.add("is-open");
  $(id).setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeModal(id) {
  $(id).classList.remove("is-open");
  $(id).setAttribute("aria-hidden", "true");
  if (!document.querySelector(".modal-shell.is-open")) {
    document.body.classList.remove("modal-open");
  }
}

function resetVoiceModal() {
  $("voiceModalForm").reset();
  state.pendingVoiceAsset = null;
  setText("voiceHashValue", "-");
  setText("voiceHashStatus", "选择语音文件后，前端会计算 hash，并先向后端检查是否已存在。");
  setText("voiceAssetStatus", "命中已有资源或上传完成后，可以先试听再点击添加。");
  setFormMessage("voiceModalMessage", "", false);
  const preview = $("voiceModalPreview");
  preview.src = "";
  preview.load();
}

function openVoiceModal() {
  resetVoiceModal();
  openModal("voiceModal");
}

function openTaskModal() {
  $("taskForm").reset();
  setFormMessage("formMessage", "", false);
  renderTaskForm();
  openModal("taskModal");
}

function openConfirmDialog({ title, message, confirmLabel = "确认" }) {
  $("confirmTitle").textContent = title;
  $("confirmMessage").textContent = message;
  $("confirmOkButton").textContent = confirmLabel;
  openModal("confirmModal");
  return new Promise((resolve) => {
    state.confirmResolver = resolve;
  });
}

function resolveConfirm(result) {
  closeModal("confirmModal");
  if (state.confirmResolver) {
    state.confirmResolver(result);
    state.confirmResolver = null;
  }
}

function renderModelProfileHint() {
  const container = $("modelProfileHint");
  const model = selectedModel();
  if (!model) {
    container.innerHTML = '<p class="muted">当前没有可用模型。</p>';
    return;
  }

  const profile = model.profile || {};
  const segmentation = profile.segmentation || {};
  const metricHtml = [
    { label: "版本", value: profile.version || "-" },
    { label: "输入模式", value: inputModeLabel(model) },
    { label: "分段上限", value: `${segmentation.max_chars_per_segment || "-"} 字符` },
    { label: "目标 token", value: segmentation.target_input_tokens || segmentation.max_input_tokens || "-" },
    { label: "参考音频", value: model.requires_reference ? `${profile.min_reference_audio_seconds || 0}s 起` : "不必需" },
  ]
    .map((item) => `
      <div class="summary-item">
        <span class="meta-label">${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
      </div>
    `)
    .join("");

  container.innerHTML = `
    <div class="section-header-spread">
      <div>
        <p class="section-kicker">Model profile</p>
        <h2>${escapeHtml(model.label)}</h2>
      </div>
      <span class="status-pill ${model.enabled ? "status-completed" : "status-failed"}">${escapeHtml(model.service_status || "unknown")}</span>
    </div>
    <p class="muted">${escapeHtml(segmentation.notes || model.description || "模型服务将通过 profile API 告知主服务如何安全分段。")}</p>
    <div class="profile-metrics">${metricHtml}</div>
  `;
}

async function loadHealth() {
  try {
    const payload = await requestJson("/api/health");
    renderAppHeading(payload.app || {});
    $("healthBadge").textContent = `默认模型 ${payload.default_model}`;
    setConnectionState(true, "连接正常");
    clearConnectionWarning();
    state.networkFailures = 0;
    state.pollInterval = (payload.poll_interval_seconds || 3) * 1000;
  } catch (error) {
    state.networkFailures += 1;
    setConnectionState(false, "网络异常，正在重试");
    reportConnectionWarning(error, "应用健康检查");
  }
}

async function loadModels() {
  try {
    const payload = await requestJson("/api/models");
    state.models = payload.items;
    state.modelMap = new Map(payload.items.map((item) => [item.name, item]));
    const select = $("modelName");
    const currentValue = select.value;
    select.innerHTML = "";

    payload.items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.name;
      option.textContent = item.enabled ? item.label : `${item.label}（不可用）`;
      option.disabled = !item.enabled;
      option.selected = item.name === currentValue || (!currentValue && item.name === payload.default);
      select.appendChild(option);
    });

    renderTaskForm();
  } catch (error) {
    reportUiError(error, {
      title: "加载模型列表失败",
      source: "模型列表",
    });
  }
}

async function loadVoiceProfiles() {
  try {
    const payload = await requestJson("/api/voice-profiles");
    state.voiceProfiles = payload.items || [];
    const select = $("voiceProfile");
    const current = select.value;
    select.innerHTML = '<option value="">直接使用上传音频</option>';
    state.voiceProfiles.forEach((profile) => {
      const option = document.createElement("option");
      option.value = profile.name;
      option.textContent = profile.name;
      option.selected = profile.name === current;
      select.appendChild(option);
    });
    renderProfileList();
    if (state.selectedProfileName) {
      const profile = selectedProfile();
      populateProfileEditor(profile);
    } else {
      populateProfileEditor(null);
    }
  } catch (error) {
    reportUiError(error, {
      title: "加载语音配置失败",
      source: "语音配置",
    });
  }
}

function renderTaskSummary() {
  const counts = {
    total: state.tasks.length,
    running: state.tasks.filter((task) => task.status === "running").length,
    failed: state.tasks.filter((task) => task.status === "failed").length,
    completed: state.tasks.filter((task) => task.status === "completed").length,
  };
  $("taskSummaryBar").innerHTML = [
    { label: "总任务数", value: counts.total },
    { label: "执行中", value: counts.running },
    { label: "失败", value: counts.failed },
    { label: "已完成", value: counts.completed },
  ]
    .map((item) => `
      <article class="summary-card">
        <p class="meta-label">${escapeHtml(item.label)}</p>
        <strong>${escapeHtml(item.value)}</strong>
      </article>
    `)
    .join("");
}

function renderProfileList() {
  const container = $("profileList");
  if (state.voiceProfiles.length === 0) {
    container.innerHTML = '<div class="empty-state">还没有语音配置，先新建一个。</div>';
    return;
  }

  container.innerHTML = state.voiceProfiles
    .map((profile) => `
      <article class="profile-row ${profile.name === state.selectedProfileName ? "is-selected" : ""}">
        <div class="profile-row-main" data-profile-name="${escapeHtml(profile.name)}">
          <h3 class="profile-row-title">${escapeHtml(profile.name)}</h3>
          <p class="task-meta">${escapeHtml(profile.language || "auto")} · ${escapeHtml(profile.description || "未填写说明")}</p>
        </div>
        <div class="profile-row-actions">
          <button class="task-mini-button" type="button" data-action="play-profile" data-profile-name="${escapeHtml(profile.name)}" data-tooltip="播放这个语音配置的参考音频">播放</button>
        </div>
      </article>
    `)
    .join("");
}

function populateProfileEditor(profile) {
  $("profileEditorTitle").textContent = profile ? `编辑 ${profile.name}` : "选择一个语音配置";
  $("profileName").value = profile?.name || "";
  $("profileLanguage").value = profile?.language || "auto";
  $("profileDescription").value = profile?.description || "";
  $("profileHash").value = profile?.metadata?.reference_audio_hash || "";
  $("profileAudioStatus").textContent = profile
    ? `参考音频：${profile.metadata?.original_filename || profile.reference_audio || "已保存资源"}`
    : "选择一个语音配置后，可直接播放参考音频检查音效。";
  const preview = $("profilePreview");
  preview.src = profile?.audio_url || "";
  preview.load();
  $("deleteProfileButton").disabled = !profile;
  $("saveProfileButton").disabled = !profile;
  $("playProfileButton").disabled = !profile;
  setFormMessage("profileMessage", "", false);
}

async function loadTasks() {
  try {
    const payload = await requestJson("/api/tasks");
    state.tasks = payload.items || [];
    renderTaskSummary();
    renderTaskTable();
    if (state.selectedTaskId) {
      await loadTaskDetail(state.selectedTaskId, { preserveTab: true, keepSelection: true });
    }
    setConnectionState(true, "连接正常");
    clearConnectionWarning();
  } catch (error) {
    state.networkFailures += 1;
    setConnectionState(false, "网络异常，正在重试");
    reportConnectionWarning(error, "任务列表轮询");
  }
}

function renderTaskTable() {
  const tbody = $("taskTableBody");
  const empty = $("taskListEmpty");
  if (state.tasks.length === 0) {
    tbody.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  tbody.innerHTML = state.tasks
    .map((task) => `
      <tr class="task-row ${task.id === state.selectedTaskId ? "is-selected" : ""}" data-task-id="${task.id}">
        <td>
          <p class="task-name">${escapeHtml(task.source_name)}</p>
          <p class="task-meta">任务 ${escapeHtml(task.id)}</p>
        </td>
        <td>${escapeHtml(task.model_name)}</td>
        <td><span class="status-pill status-${escapeHtml(task.status)}">${escapeHtml(task.status)}</span></td>
        <td>
          <div class="progress-track"><div class="progress-fill" style="width:${Number(task.progress || 0)}%;"></div></div>
          <p class="task-meta">${task.completed_segments}/${task.total_segments} 段 · ${Number(task.progress || 0)}%</p>
        </td>
        <td>${escapeHtml(formatDate(task.updated_at))}</td>
        <td>
          <div class="task-table-actions">
            ${["failed", "paused"].includes(task.status) ? `
              <button class="task-mini-icon-button is-play" type="button" data-action="resume" data-task-id="${task.id}" data-tooltip="继续执行当前任务" aria-label="继续任务">
                ${iconMarkup("play")}
              </button>
            ` : ""}
            ${["queued", "running"].includes(task.status) ? `
              <button class="task-mini-icon-button is-pause" type="button" data-action="pause" data-task-id="${task.id}" data-tooltip="暂停当前任务" aria-label="暂停任务">
                ${iconMarkup("pause")}
              </button>
            ` : ""}
          </div>
        </td>
      </tr>
    `)
    .join("");
}

function buildTaskParameterGroups(task) {
  const metadata = task.metadata || {};
  const modelProfile = metadata.model_profile || {};
  const synthesisOptions = metadata.synthesis_options || {};
  const inputFields = Array.isArray(modelProfile.task_inputs) ? modelProfile.task_inputs : [];
  const inputMode = inputModeLabel({
    requires_reference: Boolean(modelProfile.requires_reference),
    profile: modelProfile,
  });

  const groups = [
    {
      title: "任务上下文",
      items: [
        { label: "任务 ID", value: task.id },
        { label: "输入模式", value: inputMode },
        { label: "源文件", value: task.source_name },
        { label: "文件类型", value: task.source_type || "-" },
        { label: "创建时间", value: formatDate(task.created_at) },
        { label: "更新时间", value: formatDate(task.updated_at) },
      ],
    },
    {
      title: "参考设置",
      items: [
        { label: "语言", value: languageLabel(task.language || "auto") },
        { label: "语音配置", value: task.voice_profile || "直接使用上传音频" },
        { label: "参考音频", value: task.voice_path ? pathTail(task.voice_path) : "未使用" },
        { label: "输出目录", value: task.output_dir || "-", wide: true },
      ],
    },
  ];

  if (inputFields.length) {
    groups.push({
      title: "模型输入参数",
      items: inputFields.map((field) => {
        const hasValue = Object.prototype.hasOwnProperty.call(synthesisOptions, field.name);
        const rawValue = hasValue ? synthesisOptions[field.name] : field.default;
        return {
          label: field.label || field.name,
          value: formatTaskValue(rawValue),
          wide: field.type === "textarea",
        };
      }),
    });
  }

  return groups
    .filter((group) => group.items.length)
    .map(
      (group) => `
        <section class="task-detail-group">
          <p class="task-detail-group-title">${escapeHtml(group.title)}</p>
          <div class="task-detail-grid">
            ${group.items
              .map(
                (item) => `
                  <div class="task-detail-item ${item.wide ? "is-wide" : ""}">
                    <span class="meta-label">${escapeHtml(item.label)}</span>
                    <strong>${escapeHtml(formatTaskValue(item.value))}</strong>
                  </div>
                `
              )
              .join("")}
          </div>
        </section>
      `
    )
    .join("");
}

function renderTaskDrawer() {
  const drawer = $("taskDrawer");
  if (!state.selectedTaskDetail) {
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    return;
  }
  drawer.classList.add("is-open");
  drawer.setAttribute("aria-hidden", "false");

  const task = state.selectedTaskDetail;
  $("drawerTaskTitle").textContent = task.source_name;
  $("drawerStatusTab").classList.toggle("is-active", state.activeDrawerTab === "status");
  $("drawerFilesTab").classList.toggle("is-active", state.activeDrawerTab === "files");
  $("drawerStatusTab").setAttribute("aria-selected", state.activeDrawerTab === "status" ? "true" : "false");
  $("drawerFilesTab").setAttribute("aria-selected", state.activeDrawerTab === "files" ? "true" : "false");
  $("drawerStatusPanel").classList.toggle("hidden", state.activeDrawerTab !== "status");
  $("drawerFilesPanel").classList.toggle("hidden", state.activeDrawerTab !== "files");

  $("drawerSummary").innerHTML = [
    { label: "状态", value: task.status },
    { label: "模型", value: task.model_name },
    { label: "进度", value: `${task.completed_segments}/${task.total_segments}` },
    { label: "完成度", value: `${Number(task.progress || 0)}%` },
    { label: "语言", value: languageLabel(task.language || "auto") },
    { label: "最近错误", value: task.recent_error || task.error_message || "无" },
  ]
    .map((item) => `
      <div class="summary-item">
        <span class="meta-label">${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
      </div>
    `)
    .join("");
  $("drawerTaskParameters").innerHTML = buildTaskParameterGroups(task);

  const artifactBySegmentId = new Map(state.artifacts.map((artifact) => [artifact.segment_id, artifact]));
  const artifactByFileName = new Map(state.artifacts.map((artifact) => [artifact.file_name, artifact]));
  const timelineList = $("taskTimelineList");
  const segments = task.segments || [];
  if (segments.length === 0) {
    timelineList.innerHTML = '<div class="empty-state">暂无分段信息。</div>';
    return;
  }

  timelineList.innerHTML = segments
    .map((segment) => {
      const artifact = artifactBySegmentId.get(segment.segment_id) || artifactByFileName.get(segment.audio_path || "");
      const status = String(segment.status || "queued");
      const errored = ["failed", "error"].includes(status);
      const waiting = status !== "completed" && !errored;
      const textPreview = String(segment.text || "").trim();
      const textLine = textPreview ? `<p class="task-timeline-copy">${escapeHtml(textPreview)}</p>` : "";
      const meta = [];
      meta.push(`<span class="timeline-chip">${escapeHtml(segment.segment_id || "segment")}</span>`);
      meta.push(`<span class="timeline-chip">${escapeHtml(status)}</span>`);
      if (artifact?.file_name) {
        meta.push(`<span class="timeline-chip">${escapeHtml(artifact.file_name)}</span>`);
      }
      if (artifact?.size) {
        meta.push(`<span class="timeline-chip">${escapeHtml(formatBytes(artifact.size))}</span>`);
      }
      if (segment.error) {
        meta.push(`<span class="timeline-chip">${escapeHtml(segment.error)}</span>`);
      }

      let actions = "";
      if (status === "completed" && artifact?.download_url && artifact?.file_name) {
        actions = `
          <div class="timeline-actions">
            <button class="flat-icon-button is-play" type="button" data-action="play-artifact" data-audio-url="${escapeHtml(artifact.download_url)}" data-tooltip="播放这个输出音频" aria-label="播放音频">
              ${iconMarkup("play")}
            </button>
            <button class="flat-icon-button is-delete" type="button" data-action="delete-artifact" data-file-name="${escapeHtml(artifact.file_name)}" data-tooltip="删除这个输出音频" aria-label="删除音频">
              ${iconMarkup("trash")}
            </button>
          </div>
        `;
      } else if (errored) {
        actions = `
          <div class="timeline-actions">
            <span class="flat-status-icon is-error" aria-hidden="true">${iconMarkup("error")}</span>
            <button class="inline-action-button is-resume" type="button" data-action="resume-task" data-task-id="${escapeHtml(task.id)}" data-tooltip="重新开始当前任务">重新开始</button>
          </div>
        `;
      } else if (waiting) {
        actions = `<div class="timeline-actions"><span class="flat-status-icon is-waiting" aria-hidden="true" data-tooltip="等待该分段完成">${iconMarkup("wait")}</span></div>`;
      }

      return `
        <article class="task-timeline-item">
          <div class="task-timeline-main">
            <div class="task-timeline-head">
              <p class="task-timeline-name">${escapeHtml(segment.segment_id || "segment")}</p>
              <span class="status-pill status-${escapeHtml(status)}">${escapeHtml(status)}</span>
            </div>
            ${textLine}
            <div class="task-timeline-meta">${meta.join("")}</div>
          </div>
          ${actions}
        </article>
      `;
    })
    .join("");
}

function iconMarkup(name) {
  switch (name) {
    case "play":
      return '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.75v10.5L13 8 4 2.75Z"></path></svg>';
    case "pause":
      return '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3h2.5v10H5z"></path><path d="M8.5 3H11v10H8.5z"></path></svg>';
    case "trash":
      return '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 4.5h9"></path><path d="M6 2.75h4"></path><path d="M5 4.5v7"></path><path d="M8 4.5v7"></path><path d="M11 4.5v7"></path><path d="M4.5 4.5l.5 8h6l.5-8"></path></svg>';
    case "wait":
      return '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3.25v4.5l2.75 1.5"></path><circle cx="8" cy="8" r="5.25"></circle></svg>';
    case "error":
      return '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 4.25v4.5"></path><path d="M8 11.5h.01"></path><path d="M8 1.75l6 10.5H2l6-10.5Z"></path></svg>';
    default:
      return "";
  }
}

function playArtifact(url) {
  const audio = new Audio(url);
  audio.play().catch(() => {});
}

function switchDrawerTab(tabName) {
  if (!["status", "files"].includes(tabName)) {
    return;
  }
  state.activeDrawerTab = tabName;
  renderTaskDrawer();
}

function closeTaskDrawer() {
  state.taskDetailRequestVersion += 1;
  state.selectedTaskId = null;
  state.selectedTaskDetail = null;
  state.artifacts = [];
  state.selectedArtifacts = new Set();
  renderTaskTable();
  renderTaskDrawer();
}

async function loadTaskDetail(taskId, options = {}) {
  const preserveTab = options.preserveTab ?? Boolean(state.selectedTaskDetail && state.selectedTaskId === taskId);
  const keepSelection = options.keepSelection ?? preserveTab;
  state.taskDetailRequestVersion += 1;
  const requestVersion = state.taskDetailRequestVersion;

  try {
    const detail = await requestJson(`/api/tasks/${taskId}`);
    const artifactPayload = await requestJson(`/api/tasks/${taskId}/artifacts`);
    if (requestVersion !== state.taskDetailRequestVersion) {
      return;
    }

    state.selectedTaskId = taskId;
    state.selectedTaskDetail = detail;
    state.artifacts = artifactPayload.items || [];
    if (!preserveTab) {
      state.activeDrawerTab = "status";
    }
    if (!keepSelection) {
      state.selectedArtifacts = new Set();
    } else {
      state.selectedArtifacts = new Set(
        [...state.selectedArtifacts].filter((fileName) => state.artifacts.some((item) => item.file_name === fileName))
      );
    }
    renderTaskTable();
    renderTaskDrawer();
  } catch (error) {
    reportUiError(error, {
      title: "加载任务详情失败",
      source: "任务详情",
    });
  }
}

function triggerBlobDownload(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function digestFile(file) {
  if (!window.crypto?.subtle) {
    throw new Error("当前浏览器不支持文件 hash 计算");
  }
  const buffer = await file.arrayBuffer();
  const digest = await window.crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function prepareVoiceAsset(file) {
  if (!file) {
    state.pendingVoiceAsset = null;
    return;
  }
  setFormMessage("voiceModalMessage", "", false);
  setText("voiceHashStatus", "正在计算文件 hash，并向后台检查是否已有匹配资源...");
  setText("voiceAssetStatus", "请稍候，资源检查完成后即可试听或添加。");
  const hash = await digestFile(file);
  setText("voiceHashValue", hash);

  const lookup = await requestJson("/api/voice-assets/lookup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_hash: hash }),
  });

  if (lookup.exists) {
    state.pendingVoiceAsset = lookup.asset;
    setText("voiceHashStatus", "已匹配后台现有语音资源，无需重复上传。");
  } else {
    const formData = new FormData();
    formData.append("file_hash", hash);
    formData.append("asset_file", file);
    const uploadResult = await requestJson("/api/voice-assets", {
      method: "POST",
      body: formData,
    });
    state.pendingVoiceAsset = uploadResult.asset;
    setText("voiceHashStatus", "后台未命中同 hash 资源，已完成上传并建立预览。");
  }

  $("voiceModalPreview").src = state.pendingVoiceAsset.audio_url;
  $("voiceModalPreview").load();
  setText("voiceAssetStatus", `当前资源：${state.pendingVoiceAsset.original_name}`);
}

async function downloadSelectedArtifacts() {
  if (!state.selectedTaskId || state.selectedArtifacts.size === 0) {
    return;
  }
  const blob = await requestBlob(`/api/tasks/${state.selectedTaskId}/artifacts/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ files: [...state.selectedArtifacts] }),
  });
  triggerBlobDownload(blob, `${state.selectedTaskId}-artifacts.zip`);
}

async function deleteArtifacts(files) {
  if (!state.selectedTaskId || files.length === 0) {
    return;
  }
  await requestJson(`/api/tasks/${state.selectedTaskId}/artifacts/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ files }),
  });
  files.forEach((fileName) => state.selectedArtifacts.delete(fileName));
  await loadTaskDetail(state.selectedTaskId, { keepSelection: true });
  await loadTasks();
}

async function submitTask(event) {
  event.preventDefault();
  setFormMessage("formMessage", "正在提交...", false);
  try {
    const model = selectedModel();
    if (!model) {
      throw new Error("当前没有可用模型");
    }

    const profile = selectedModelProfile();
    const formData = new FormData(event.target);
    const dynamicInputs = profile.task_inputs || [];
    dynamicInputs.forEach((field) => {
      if (field.type === "checkbox") {
        const element = $(taskInputId(field.name));
        if (element?.checked) {
          formData.set(field.name, "true");
        } else {
          formData.delete(field.name);
        }
        return;
      }

      const rawValue = String(formData.get(field.name) || "").trim();
      if (field.required && !rawValue) {
        throw new Error(`${field.label || field.name}不能为空`);
      }
      if (rawValue) {
        formData.set(field.name, rawValue);
      } else {
        formData.delete(field.name);
      }
    });

    const voiceProfileValue = String(formData.get("voice_profile") || "").trim();
    const hasVoiceFile = $("voiceFile")?.files?.length > 0;
    if (model.requires_reference) {
      if (!hasVoiceFile && !voiceProfileValue) {
        throw new Error("当前模型需要参考音频或已保存语音配置");
      }
    } else {
      formData.delete("voice_file");
      formData.set("voice_profile", "");
    }

    if (model.name === "qwen3_tts_base") {
      const xVectorOnly = $(taskInputId("x_vector_only_mode"))?.checked || false;
      const referenceText = String(formData.get("reference_text") || "").trim();
      if (!xVectorOnly && !referenceText) {
        throw new Error("Qwen3-TTS Base 在未启用 x-vector only 时必须填写参考音频文本");
      }
    }

    await requestJson("/api/tasks", { method: "POST", body: formData });
    setFormMessage("formMessage", "任务已提交。", false);
    event.target.reset();
    renderTaskForm();
    closeModal("taskModal");
    await loadTasks();
  } catch (error) {
    reportUiError(error, {
      title: "提交任务失败",
      source: "任务创建",
      formMessageId: "formMessage",
    });
  }
}

async function submitProfileEditor(event) {
  event.preventDefault();
  const profile = selectedProfile();
  if (!profile) {
    return;
  }
  setFormMessage("profileMessage", "正在保存...", false);
  const formData = new FormData();
  formData.append("name", profile.name);
  formData.append("language", $("profileLanguage").value);
  formData.append("description", $("profileDescription").value.trim());
  if (profile.metadata?.reference_audio_hash) {
    formData.append("reference_audio_hash", profile.metadata.reference_audio_hash);
  }
  try {
    const saved = await requestJson("/api/voice-profiles", {
      method: "POST",
      body: formData,
    });
    state.selectedProfileName = saved.name;
    setFormMessage("profileMessage", "语音配置已保存。", false);
    await loadVoiceProfiles();
    const selected = state.voiceProfiles.find((item) => item.name === saved.name) || saved;
    populateProfileEditor(selected);
  } catch (error) {
    reportUiError(error, {
      title: "保存语音配置失败",
      source: "语音配置编辑",
      formMessageId: "profileMessage",
    });
  }
}

async function submitVoiceModal(event) {
  event.preventDefault();
  if (!state.pendingVoiceAsset) {
    reportUiError(new Error("请先选择语音文件并等待 hash 匹配或上传完成。"), {
      title: "添加语音失败",
      source: "语音资源",
      formMessageId: "voiceModalMessage",
    });
    return;
  }

  setFormMessage("voiceModalMessage", "正在创建语音配置...", false);
  const formData = new FormData();
  formData.append("name", $("voiceModalName").value.trim());
  formData.append("language", $("voiceModalLanguage").value);
  formData.append("description", $("voiceModalDescription").value.trim());
  formData.append("reference_audio_hash", state.pendingVoiceAsset.file_hash);

  try {
    const profile = await requestJson("/api/voice-profiles", { method: "POST", body: formData });
    state.selectedProfileName = profile.name;
    closeModal("voiceModal");
    await loadVoiceProfiles();
    populateProfileEditor(selectedProfile());
    switchTab("profiles");
  } catch (error) {
    reportUiError(error, {
      title: "创建语音配置失败",
      source: "语音资源",
      formMessageId: "voiceModalMessage",
    });
  }
}

function switchTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tab === tabName);
  });
  document.querySelectorAll(".workspace").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `${tabName}Tab`);
  });
}

function hideTooltip() {
  const tooltip = $("tooltipBubble");
  tooltip.classList.remove("is-visible");
  tooltip.setAttribute("aria-hidden", "true");
  if (state.tooltipTimer) {
    window.clearTimeout(state.tooltipTimer);
    state.tooltipTimer = null;
  }
  state.tooltipTarget = null;
}

function positionTooltip(x, y) {
  const tooltip = $("tooltipBubble");
  const width = tooltip.offsetWidth || 160;
  const height = tooltip.offsetHeight || 44;
  const left = Math.min(window.innerWidth - width - 14, x + 18);
  const top = Math.min(window.innerHeight - height - 14, y + 22);
  tooltip.style.left = `${Math.max(12, left)}px`;
  tooltip.style.top = `${Math.max(12, top)}px`;
}

function scheduleTooltip(target) {
  hideTooltip();
  state.tooltipTarget = target;
  state.tooltipTimer = window.setTimeout(() => {
    if (!state.tooltipTarget) {
      return;
    }
    const tooltip = $("tooltipBubble");
    tooltip.textContent = state.tooltipTarget.dataset.tooltip;
    tooltip.classList.add("is-visible");
    tooltip.setAttribute("aria-hidden", "false");
    positionTooltip(state.pointerX, state.pointerY);
  }, 2000);
}

function attachTooltipSystem() {
  document.addEventListener("mousemove", (event) => {
    state.pointerX = event.clientX;
    state.pointerY = event.clientY;
    if ($("tooltipBubble").classList.contains("is-visible")) {
      positionTooltip(event.clientX, event.clientY);
    }
  });

  document.addEventListener("mouseover", (event) => {
    const target = event.target.closest("[data-tooltip]");
    if (!target || target === state.tooltipTarget) {
      return;
    }
    scheduleTooltip(target);
  });

  document.addEventListener("mouseout", (event) => {
    const target = event.target.closest("[data-tooltip]");
    const related = event.relatedTarget?.closest?.("[data-tooltip]") || null;
    if (target && target === state.tooltipTarget && related !== target) {
      hideTooltip();
    }
  });

  document.addEventListener("mousedown", hideTooltip);
  document.addEventListener("scroll", hideTooltip, true);
}

function startPollingLoop() {
  const tick = async () => {
    await loadHealth();
    await loadTasks();
    setTimeout(tick, state.pollInterval);
  };
  setTimeout(tick, state.pollInterval);
}

function attachDrawerResize() {
  const handle = $("drawerResizeHandle");
  handle.addEventListener("mousedown", (event) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = state.drawerWidth;

    function onMove(moveEvent) {
      const delta = startX - moveEvent.clientX;
      updateDrawerWidth(startWidth + delta);
    }

    function onUp() {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  });
}

async function bootstrap() {
  loadCachedUiEvents();
  updateDrawerWidth(state.drawerWidth);
  attachGlobalErrorHandlers();
  attachDrawerResize();
  attachTooltipSystem();

  $("taskForm").addEventListener("submit", submitTask);
  $("profileEditorForm").addEventListener("submit", submitProfileEditor);
  $("voiceModalForm").addEventListener("submit", submitVoiceModal);
  $("refreshTasks").addEventListener("click", loadTasks);
  $("openTaskModalButton").addEventListener("click", openTaskModal);
  $("openEventLogButton").addEventListener("click", openEventLogModal);
  $("newProfileButton").addEventListener("click", openVoiceModal);
  $("modelName").addEventListener("change", renderTaskForm);
  $("drawerStatusTab").addEventListener("click", () => switchDrawerTab("status"));
  $("drawerFilesTab").addEventListener("click", () => switchDrawerTab("files"));
  $("closeDrawerButton").addEventListener("click", closeTaskDrawer);
  $("clearEventsButton").addEventListener("click", async () => {
    if (!state.uiEvents.length) {
      return;
    }
    const confirmed = await openConfirmDialog({
      title: "清空事件列表",
      message: "确认清空当前缓存的全部错误和告警事件吗？此操作不可撤销。",
      confirmLabel: "清空",
    });
    if (confirmed) {
      clearUiEvents();
    }
  });
  $("eventList").addEventListener("click", (event) => {
    const deleteButton = event.target.closest("button[data-delete-event-id]");
    if (!deleteButton) {
      return;
    }
    deleteUiEvent(deleteButton.dataset.deleteEventId);
  });
  $("eventAlertCloseButton").addEventListener("click", () => closeEventAlertDialog());
  $("eventAlertViewListButton").addEventListener("click", () => closeEventAlertDialog({ openList: true }));
  $("deleteProfileButton").addEventListener("click", async () => {
    if (!state.selectedProfileName) {
      return;
    }
    const confirmed = await openConfirmDialog({
      title: "删除语音配置",
      message: `确认删除语音配置“${state.selectedProfileName}”吗？删除前需要二次确认。`,
      confirmLabel: "删除",
    });
    if (!confirmed) {
      return;
    }
    await requestJson(`/api/voice-profiles/${state.selectedProfileName}`, { method: "DELETE" });
    state.selectedProfileName = null;
    populateProfileEditor(null);
    await loadVoiceProfiles();
  });
  $("playProfileButton").addEventListener("click", () => {
    $("profilePreview").play().catch(() => {});
  });
  $("voicePreviewButton").addEventListener("click", () => {
    $("voiceModalPreview").play().catch(() => {});
  });
  $("voiceAssetFileInput").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    try {
      await prepareVoiceAsset(file);
    } catch (error) {
      state.pendingVoiceAsset = null;
      reportUiError(error, {
        title: "处理语音文件失败",
        source: "语音资源",
        formMessageId: "voiceModalMessage",
      });
      setText("voiceHashStatus", "文件处理失败，请重新选择语音文件后再试。");
    }
  });
  $("confirmCancelButton").addEventListener("click", () => resolveConfirm(false));
  $("confirmOkButton").addEventListener("click", () => resolveConfirm(true));

  document.querySelectorAll("[data-close-modal]").forEach((element) => {
    element.addEventListener("click", () => closeModal(element.dataset.closeModal));
  });

  document.addEventListener("mousedown", (event) => {
    if (!state.selectedTaskDetail) {
      return;
    }
    const drawerPanel = document.querySelector(".drawer-panel");
    const taskRow = event.target.closest("tr[data-task-id]");
    const buttonInsideDrawer = event.target.closest("#closeDrawerButton, #drawerResizeHandle, [data-drawer-tab]");
    if (buttonInsideDrawer || taskRow) {
      return;
    }
    if (drawerPanel && !drawerPanel.contains(event.target)) {
      closeTaskDrawer();
    }
  });

  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });

  $("taskTableBody").addEventListener("click", async (event) => {
    const actionButton = event.target.closest("button[data-action]");
    if (actionButton) {
      event.stopPropagation();
      await requestJson(`/api/tasks/${actionButton.dataset.taskId}/${actionButton.dataset.action}`, { method: "POST" });
      await loadTasks();
      return;
    }
    const row = event.target.closest("tr[data-task-id]");
    if (!row) {
      return;
    }
    await loadTaskDetail(row.dataset.taskId, { preserveTab: false, keepSelection: false });
  });

  $("taskTimelineList").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }

    if (button.dataset.action === "play-artifact") {
      playArtifact(button.dataset.audioUrl);
      return;
    }

    if (button.dataset.action === "delete-artifact") {
      const confirmed = await openConfirmDialog({
        title: "删除音频文件",
        message: `确认删除音频文件“${button.dataset.fileName}”吗？`,
        confirmLabel: "删除",
      });
      if (confirmed) {
        await deleteArtifacts([button.dataset.fileName]);
      }
      return;
    }

    if (button.dataset.action === "resume-task") {
      await requestJson(`/api/tasks/${button.dataset.taskId}/resume`, { method: "POST" });
      await loadTasks();
      if (state.selectedTaskId === button.dataset.taskId && state.selectedTaskDetail) {
        switchDrawerTab("files");
      }
    }
  });

  $("profileList").addEventListener("click", (event) => {
    const playButton = event.target.closest("button[data-action='play-profile']");
    const card = event.target.closest("[data-profile-name]");
    if (playButton) {
      const profile = state.voiceProfiles.find((item) => item.name === playButton.dataset.profileName);
      if (profile) {
        state.selectedProfileName = profile.name;
        populateProfileEditor(profile);
        renderProfileList();
        const preview = $("profilePreview");
        preview.play().catch(() => {});
      }
      return;
    }
    if (card) {
      const profile = state.voiceProfiles.find((item) => item.name === card.dataset.profileName);
      if (profile) {
        state.selectedProfileName = profile.name;
        populateProfileEditor(profile);
        renderProfileList();
      }
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal("taskModal");
      closeModal("voiceModal");
      closeModal("eventLogModal");
      closeEventAlertDialog();
      resolveConfirm(false);
    }
  });

  await loadHealth();
  await loadModels();
  await loadVoiceProfiles();
  populateProfileEditor(null);
  await loadTasks();
  startPollingLoop();
}

bootstrap().catch((error) => {
  reportUiError(error, {
    title: "界面初始化失败",
    source: "前端启动",
  });
});