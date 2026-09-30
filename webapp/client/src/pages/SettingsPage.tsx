import { Button, theme } from "antd";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useTheme } from "../theme";
import { textOnPrimary } from "../themes";
import { useI18n } from "../i18n";
import ModelsPage from "./ModelsPage";
import VoicesPage from "./VoicesPage";
import DisplaySettingsPage from "./DisplaySettingsPage";
import UserSettingsPage from "./UserSettingsPage";

/** 设置页：左侧子导航（模型/声音/显示/用户）+ 右侧面板。 */
export default function SettingsPage() {
  const { t } = useI18n();
  const { palette } = useTheme();
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const items = [
    { key: "models", label: t("nav.models") },
    { key: "voices", label: t("nav.voices") },
    { key: "display", label: t("settings.display") },
    { key: "account", label: t("nav.settings") },
  ];
  const active = items.find((item) => pathname.startsWith(`/settings/${item.key}`))?.key ?? "models";
  const onPrimary = textOnPrimary(palette.primary);

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
      <nav style={{ flex: "0 0 180px", display: "flex", flexDirection: "column", gap: 8 }}>
        {items.map((item) => {
          const isActive = item.key === active;
          return (
            <Button
              key={item.key}
              block
              variant="outlined"
              style={{
                textAlign: "left",
                borderColor: isActive ? palette.primary : token.colorBorder,
                background: isActive ? palette.primary : "transparent",
                color: isActive ? onPrimary : undefined,
              }}
              onClick={() => navigate(`/settings/${item.key}`)}
            >
              {item.label}
            </Button>
          );
        })}
      </nav>

      <div style={{ flex: 1, minWidth: 0 }}>
        <Routes>
          <Route index element={<Navigate to="models" replace />} />
          <Route path="models" element={<ModelsPage />} />
          <Route path="voices" element={<VoicesPage />} />
          <Route path="display" element={<DisplaySettingsPage />} />
          <Route path="account" element={<UserSettingsPage />} />
          <Route path="*" element={<Navigate to="models" replace />} />
        </Routes>
      </div>
    </div>
  );
}
