import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { DEFAULT_THEME_ID, findTheme, THEMES, type ThemePalette } from "./themes";

const THEME_KEY = "vc_theme";
const FONT_KEY = "vc_font_scale";

/** 可选界面字号倍数（显示设置用）。 */
export const FONT_SCALES = [0.9, 1, 1.15, 1.3] as const;

interface ThemeValue {
  /** 当前配色方案 */
  palette: ThemePalette;
  paletteId: string;
  setPaletteId: (id: string) => void;
  palettes: ThemePalette[];
  /** 便捷：当前是否暗色方案 */
  dark: boolean;
  /** 界面字号倍数 */
  fontScale: number;
  setFontScale: (scale: number) => void;
}

const ThemeContext = createContext<ThemeValue>({
  palette: findTheme(DEFAULT_THEME_ID),
  paletteId: DEFAULT_THEME_ID,
  setPaletteId: () => {},
  palettes: THEMES,
  dark: false,
  fontScale: 1,
  setFontScale: () => {},
});

/** 读取持久化字号；仅接受预设档位，非法值回退 1。 */
function readFontScale(): number {
  const stored = Number(localStorage.getItem(FONT_KEY));
  return (FONT_SCALES as readonly number[]).includes(stored) ? stored : 1;
}

function clampFontScale(scale: number): number {
  return (FONT_SCALES as readonly number[]).includes(scale) ? scale : 1;
}

/** 读取持久化的方案；兼容旧值 "light" / "dark"。 */
function readPaletteId(): string {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light") return DEFAULT_THEME_ID;
  if (stored === "dark") return "dark";
  return findTheme(stored).id;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [paletteId, setPaletteIdState] = useState<string>(() => readPaletteId());
  const [fontScale, setFontScaleState] = useState<number>(() => readFontScale());

  useEffect(() => {
    localStorage.setItem(THEME_KEY, paletteId);
  }, [paletteId]);

  useEffect(() => {
    localStorage.setItem(FONT_KEY, String(fontScale));
  }, [fontScale]);

  const setPaletteId = useCallback((id: string) => setPaletteIdState(findTheme(id).id), []);
  const setFontScale = useCallback((scale: number) => setFontScaleState(clampFontScale(scale)), []);

  const value = useMemo<ThemeValue>(() => {
    const palette = findTheme(paletteId);
    return {
      palette,
      paletteId: palette.id,
      setPaletteId,
      palettes: THEMES,
      dark: palette.dark,
      fontScale,
      setFontScale,
    };
  }, [paletteId, setPaletteId, fontScale, setFontScale]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}
