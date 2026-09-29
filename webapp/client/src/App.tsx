import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Button, Dropdown, Layout, Menu, Space, Typography } from "antd";
import {
  FolderOpenOutlined,
  SettingOutlined,
  AudioOutlined,
  BgColorsOutlined,
  UserOutlined,
  SoundOutlined,
  LogoutOutlined,
} from "@ant-design/icons";
import { useAuth } from "./auth";
import { useTheme } from "./theme";
import { useI18n } from "./i18n";
import type { Messages } from "./i18n/locales";
import LoginPage from "./pages/LoginPage";
import TasksPage from "./pages/TasksPage";
import ModelsPage from "./pages/ModelsPage";
import VoicesPage from "./pages/VoicesPage";
import UserSettingsPage from "./pages/UserSettingsPage";

const { Sider, Content } = Layout;

export default function App() {
  const { token, logout } = useAuth();
  const { palette, paletteId, setPaletteId, palettes } = useTheme();
  const { t } = useI18n();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  if (!token) return <LoginPage />;

  const menuItems = [
    { key: "tasks", icon: <FolderOpenOutlined />, label: t("nav.tasks") },
    { key: "models", icon: <SettingOutlined />, label: t("nav.models") },
    { key: "voices", icon: <SoundOutlined />, label: t("nav.voices") },
    { key: "settings", icon: <UserOutlined />, label: t("nav.settings") },
  ];

  // 导航高亮由路由派生，刷新/前进后退都能保持一致
  const selected =
    menuItems.find((item) => pathname.startsWith(`/${item.key}`))?.key ?? "tasks";

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
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/voices" element={<VoicesPage />} />
          <Route path="/settings" element={<UserSettingsPage />} />
          <Route path="*" element={<Navigate to="/tasks" replace />} />
        </Routes>
      </Content>
    </Layout>
  );
}