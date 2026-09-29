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

interface ThemeValue {
  /** 当前配色方案 */
  palette: ThemePalette;
  paletteId: string;
  setPaletteId: (id: string) => void;
  palettes: ThemePalette[];
  /** 便捷：当前是否暗色方案 */
  dark: boolean;
}

const ThemeContext = createContext<ThemeValue>({
  palette: findTheme(DEFAULT_THEME_ID),
  paletteId: DEFAULT_THEME_ID,
  setPaletteId: () => {},
  palettes: THEMES,
  dark: false,
});

/** 读取持久化的方案；兼容旧值 "light" / "dark"。 */
function readPaletteId(): string {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light") return DEFAULT_THEME_ID;
  if (stored === "dark") return "dark";
  return findTheme(stored).id;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [paletteId, setPaletteIdState] = useState<string>(() => readPaletteId());

  useEffect(() => {
    localStorage.setItem(THEME_KEY, paletteId);
  }, [paletteId]);

  const setPaletteId = useCallback((id: string) => setPaletteIdState(findTheme(id).id), []);

  const value = useMemo<ThemeValue>(() => {
    const palette = findTheme(paletteId);
    return { palette, paletteId: palette.id, setPaletteId, palettes: THEMES, dark: palette.dark };
  }, [paletteId, setPaletteId]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}
