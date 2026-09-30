import { Card, Segmented, Tag, theme, Typography } from "antd";
import { useTheme, FONT_SCALES } from "../theme";
import { backgroundContrastingWith, textOnColor, themeSwatches } from "../themes";
import { useI18n } from "../i18n";
import type { Messages } from "../i18n/locales";
import LanguageSelect from "../components/LanguageSelect";

/** 显示设置：语言、主题配色、字体字号。 */
export default function DisplaySettingsPage() {
  const { t } = useI18n();
  const { paletteId, setPaletteId, palettes, fontScale, setFontScale } = useTheme();
  const { token } = theme.useToken();

  return (
    <div>
      <Typography.Title level={4} className="page-title">
        {t("settings.display")}
      </Typography.Title>

      <Card className="flat-card" title={t("pref.language")} style={{ borderRadius: 16, marginBottom: 16 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t("pref.languageHint")}
        </Typography.Text>
        <div style={{ marginTop: 12 }}>
          <LanguageSelect />
        </div>
      </Card>

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
            // 选中卡片背景与「第一个色块（主色）」保持足够对比，避免主色块淹没在选中底色里。
            const cardBg = active
              ? backgroundContrastingWith(themeOption.primary, token.colorPrimaryBg, 3)
              : "transparent";
            const cardFg = active ? textOnColor(cardBg) : undefined;
            return (
              <div
                key={themeOption.id}
                onClick={() => setPaletteId(themeOption.id)}
                style={{
                  cursor: "pointer",
                  borderRadius: 12,
                  padding: 10,
                  border: `1px solid ${active ? themeOption.primary : token.colorBorder}`,
                  background: cardBg,
                  color: cardFg,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <Typography.Text strong style={{ color: cardFg }}>
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
                <Typography.Text
                  type={active ? undefined : "secondary"}
                  style={{ fontSize: 12, color: cardFg, opacity: active ? 0.85 : undefined }}
                >
                  {t("settings.usage", {
                    usage: t(`theme.${themeOption.id}.usage` as keyof Messages),
                  })}
                </Typography.Text>
              </div>
            );
          })}
        </div>
      </Card>

      <Card className="flat-card" title={t("pref.fontSize")} style={{ borderRadius: 16 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t("pref.fontSizeHint")}
        </Typography.Text>
        <div style={{ marginTop: 12 }}>
          <Segmented
            value={fontScale}
            onChange={(value) => setFontScale(Number(value))}
            options={FONT_SCALES.map((scale) => ({
              label: `${Math.round(scale * 100)}%`,
              value: scale,
            }))}
          />
        </div>
      </Card>
    </div>
  );
}
