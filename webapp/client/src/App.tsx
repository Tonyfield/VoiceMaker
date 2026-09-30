import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Button, Dropdown, Layout, Menu, Space, Typography } from "antd";
import {
  FolderOpenOutlined,
  SettingOutlined,
  AudioOutlined,
  BgColorsOutlined,
  CloudUploadOutlined,
  LogoutOutlined,
} from "@ant-design/icons";
import { useAuth } from "./auth";
import { useTheme } from "./theme";
import { useI18n } from "./i18n";
import type { Messages } from "./i18n/locales";
import LoginPage from "./pages/LoginPage";
import TasksPage from "./pages/TasksPage";
import TaskWorkspacePage from "./pages/TaskWorkspacePage";
import TransferPage from "./pages/TransferPage";
import SettingsPage from "./pages/SettingsPage";

const { Sider, Content } = Layout;

export default function App() {
  const { token, logout } = useAuth();
  const { palette, paletteId, setPaletteId, palettes } = useTheme();
  const { t } = useI18n();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  if (!token) return <LoginPage />;

  const menuItems = [
    { key: "tasks", icon: <FolderOpenOutlined />, label: t("nav.home") },
    { key: "transfer", icon: <CloudUploadOutlined />, label: t("nav.transfer") },
    { key: "settings", icon: <SettingOutlined />, label: t("nav.settingsPage") },
  ];

  // 导航高亮由路由派生。
  const selected = pathname.startsWith("/settings")
    ? "settings"
    : pathname.startsWith("/transfer")
      ? "transfer"
      : "tasks";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={240} theme={palette.dark ? "dark" : "light"} className="sider">
        <div className="brand-card" style={{ height: 56 }}>
          <AudioOutlined style={{ fontSize: 22, color: palette.primary }} />
          <Typography.Text strong>VoiceCloner</Typography.Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selected]}
          items={menuItems}
          onClick={({ key }) => navigate(`/${key}`)}
          style={{ borderInlineEnd: "none" }}
        />
        <div style={{ position: "absolute", bottom: 16, left: 16, right: 16 }}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Dropdown
              trigger={["click"]}
              menu={{
                items: palettes.map((themeOption) => ({
                  key: themeOption.id,
                  label: t(`theme.${themeOption.id}.name` as keyof Messages),
                })),
                selectable: true,
                selectedKeys: [paletteId],
                onClick: ({ key }) => setPaletteId(key),
              }}
            >
              <Button block icon={<BgColorsOutlined />}>
                {t(`theme.${palette.id}.name` as keyof Messages)}
              </Button>
            </Dropdown>
            <Button block icon={<LogoutOutlined />} onClick={logout}>
              {t("nav.logout")}
            </Button>
          </Space>
        </div>
      </Sider>
      <Content className="content-area">
        <Routes>
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/tasks/:id" element={<TaskWorkspacePage />} />
          <Route path="/transfer" element={<TransferPage />} />
          <Route path="/settings/*" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/tasks" replace />} />
        </Routes>
      </Content>
    </Layout>
  );
}
