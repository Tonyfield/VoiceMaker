import { useRef, useState } from "react";
import { Button, Card, Form, Input, Tag, theme, Typography, message } from "antd";
import { changePassword } from "../api/client";
import { useAuth } from "../auth";
import { useTheme } from "../theme";
import { textOnPrimary, textPrimaryOn, themeSwatches } from "../themes";
import { useI18n } from "../i18n";
import type { Messages } from "../i18n/locales";
import LanguageSelect from "../components/LanguageSelect";

export default function UserSettingsPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const { palette, paletteId, setPaletteId, palettes } = useTheme();
  const { token } = theme.useToken();
  /** 主色作为「背景上的文字/描边」时的安全色（浅色主题下自动加深，保证对比度）。 */
  const primaryText = textPrimaryOn(palette.surface, palette.primary);
  /** 实心主色上的文字（选中态）按对比度取黑/白。 */
  const onPrimary = textOnPrimary(palette.primary);
  const [saving, setSaving] = useState(false);
  const [activeSection, setActiveSection] = useState("account");

  const accountRef = useRef<HTMLDivElement | null>(null);
  const themeRef = useRef<HTMLDivElement | null>(null);
  const passwordRef = useRef<HTMLDivElement | null>(null);
  const sections = [
    { key: "account", label: t("settings.account"), ref: accountRef },
    { key: "theme", label: t("settings.theme"), ref: themeRef },
    { key: "password", label: t("settings.password"), ref: passwordRef },
  ];

  const goSection = (key: string) => {
    setActiveSection(key);
    sections
      .find((s) => s.key === key)
      ?.ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const onSave = async (values: any) => {
    setSaving(true);
    try {
      await changePassword(values.oldPassword, values.newPassword);
      message.success(t("settings.passwordChanged"));
    } catch (e: any) {
      message.error(e?.response?.data?.error || t("settings.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <Typography.Title level={4} className="page-title">
        {t("nav.settings")}
      </Typography.Title>

      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        {/* 左侧设置导航栏 */}
        <nav
          style={{
            flex: "0 0 180px",
            position: "sticky",
            top: 0,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          {sections.map((section) => {
            const active = section.key === activeSection;
            return (
              <Button
                key={section.key}
                block
                variant="outlined"
                style={{
                  textAlign: "left",
                  // 选中项用实心主色 + 对比色文字，保证「填充色/文字色」对比明显
                  borderColor: active ? palette.primary : token.colorBorder,
                  background: active ? palette.primary : "transparent",
                  color: active ? onPrimary : undefined,
                }}
                onClick={() => goSection(section.key)}
              >
                {section.label}
              </Button>
            );
          })}
        </nav>

        {/* 右侧设置面板 */}
        <div style={{ flex: 1, minWidth: 0, maxWidth: 760 }}>
          <div ref={accountRef} style={{ scrollMarginTop: 12 }}>
            <Card className="flat-card" title={t("settings.account")} style={{ borderRadius: 16, marginBottom: 16 }}>
              <Typography.Text>{t("settings.currentUser")}</Typography.Text>
              <Typography.Text strong>{user?.username}</Typography.Text>
            </Card>
          </div>

          <div style={{ scrollMarginTop: 12 }}>
            <Card className="flat-card" title={t("pref.language")} style={{ borderRadius: 16, marginBottom: 16 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t("pref.languageHint")}
              </Typography.Text>
              <div style={{ marginTop: 12 }}>
                <LanguageSelect />
              </div>
            </Card>
          </div>

          <div ref={themeRef} style={{ scrollMarginTop: 12 }}>
            <Card className="flat-card" title={t("settings.theme")} style={{ borderRadius: 16, marginBottom: 16 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t("settings.themeHint")}
              </Typography.Text>
              <div
                style={{
                  marginTop: 12,
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                  gap: 12,
                }}
              >
                {palettes.map((themeOption) => {
                  const active = themeOption.id === paletteId;
                  return (
                    <div
                      key={themeOption.id}
                      onClick={() => setPaletteId(themeOption.id)}
                      style={{
                        cursor: "pointer",
                        borderRadius: 12,
                        padding: 10,
                        border: `1px solid ${active ? palette.primary : token.colorBorder}`,
                        background: active ? token.colorPrimaryBg : "transparent",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                        <Typography.Text strong>
                          {t(`theme.${themeOption.id}.name` as keyof Messages)}
                        </Typography.Text>
                        {active && <Tag color="blue">{t("settings.current")}</Tag>}
                      </div>
                      <div style={{ display: "flex", gap: 6, margin: "8px 0" }}>
                        {themeSwatches(themeOption).map((color, i) => (
                          <span
                            key={`${color}-${i}`}
                            title={color}
                            style={{
                              width: 18,
                              height: 18,
                              borderRadius: 4,
                              background: color,
                              border: `1px solid ${token.colorBorder}`,
                            }}
                          />
                        ))}
                      </div>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {t("settings.usage", {
                          usage: t(`theme.${themeOption.id}.usage` as keyof Messages),
                        })}
                      </Typography.Text>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>

          <div ref={passwordRef} style={{ scrollMarginTop: 12 }}>
            <Card className="flat-card" title={t("settings.password")} style={{ borderRadius: 16 }}>
              <Form layout="vertical" onFinish={onSave}>
                <Form.Item name="oldPassword" label={t("settings.oldPassword")} rules={[{ required: true, message: t("settings.oldRequired") }]}>
                  <Input.Password variant="outlined" />
                </Form.Item>
                <Form.Item name="newPassword" label={t("settings.newPassword")} rules={[
                  { required: true, message: t("settings.newRequired") },
                  { min: 6, message: t("settings.min6") },
                ]}>
                  <Input.Password variant="outlined" />
                </Form.Item>
                <Form.Item name="confirm" label={t("settings.confirmPassword")} dependencies={["newPassword"]} rules={[
                  { required: true, message: t("settings.confirmRequired") },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue("newPassword") === value) return Promise.resolve();
                      return Promise.reject(new Error(t("settings.mismatch")));
                    },
                  }),
                ]}>
                  <Input.Password variant="outlined" />
                </Form.Item>
                <Button
                  color="primary"
                  variant="outlined"
                  htmlType="submit"
                  loading={saving}
                  style={{ color: primaryText, borderColor: primaryText }}
                >
                  {t("act.save")}
                </Button>
              </Form>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
