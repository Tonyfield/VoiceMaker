import { cutWords } from "./jieba";

/**
 * IndexTTS 文字增强（在把分段文本转换成 IndexTTS 输入之前执行）。
 *
 * 四项处理，可分别开启：
 *  0. 专有名词替换（entities）：按「专有名词」表的替换文本改写（长词优先）；
 *  1. 句末标点补逗号（commaAfterPunct）：在感叹号/问号（`! ！ ? ？`）后补一个逗号（全角补「，」、半角补「,」）；
 *  2. 分词间隔（wordGap）：用 jieba 分词后，在每个分词之间插入指定字符串；
 *  3. 感叹词前缀（interjectionPrefix）：在感叹词（啊/哦/呀…）前插入指定字符串。
 *
 * 判定规则（避免误伤语气助词）：
 *   - 目标字属于 `INTERJECTIONS`；
 *   - 它前面的字符是「边界」——串首、空白或标点，即**不是**汉字/字母/数字/下划线；
 *   - 前面不是已插入的前缀（避免重复插入，保证幂等）。
 *
 * 例：`啊，原来是你` → `-啊，原来是你`；`好呀` → 不变（`呀` 前是汉字）；
 *     `呀，是你` → `-呀，是你`。
 *
 * 说明：增强会写回分段文本（在分段/注音阶段执行一次），因此注音标记与增强后的文本
 * 始终对齐；送 IndexTTS 前不再重复处理。
 */

/** 常见汉语感叹词（叹词）。按需在此增删。 */
export const INTERJECTIONS = "啊哦呀哈嗨嘿哎唉咦哟噢喔喂嗯呃哇哼嘻唷咳";

/** 默认的感叹词前缀（中杠）。 */
export const DEFAULT_INTERJECTION_PREFIX = "-";

export interface EntityReplacement {
  from: string;
  to: string;
}

export interface TextEnhanceOptions {
  /** 在感叹词前插入的字符串；空/未设置表示不处理。 */
  interjectionPrefix?: string;
  /** 在分词之间插入的字符串；空/未设置表示不处理。 */
  wordGap?: string;
  /** 在感叹号/问号后补一个逗号（全角标点补「，」，半角标点补「,」）。 */
  commaAfterPunct?: boolean;
  /** 专有名词替换（长词优先；已替换过的不重复处理）。 */
  entities?: EntityReplacement[];
}

/** 从任务参数解析增强选项（复选框 + 字符填充框）。 */
export function enhanceOptionsFromParams(
  params: Record<string, unknown>
): TextEnhanceOptions {
  const interjectionEnabled = params.interjection_prefix_enabled !== false;
  const wordGapEnabled = params.word_gap_enabled === true;
  return {
    interjectionPrefix: interjectionEnabled
      ? String(params.interjection_prefix ?? DEFAULT_INTERJECTION_PREFIX)
      : undefined,
    wordGap: wordGapEnabled ? String(params.word_gap ?? DEFAULT_INTERJECTION_PREFIX) : undefined,
    commaAfterPunct: params.punct_comma_enabled === true,
  };
}

export function hasEnhancement(options: TextEnhanceOptions): boolean {
  return (
    Boolean(options.interjectionPrefix) ||
    Boolean(options.wordGap) ||
    Boolean(options.commaAfterPunct) ||
    Boolean(options.entities?.length)
  );
}

/** 专有名词替换（字面替换，长词优先；替换文本已存在则跳过，保证幂等）。 */
function applyEntityReplacements(text: string, rules: EntityReplacement[]): string {
  let out = text;
  for (const rule of rules) {
    if (!rule.from || !rule.to || rule.from === rule.to) continue;
    if (out.includes(rule.to)) continue;
    out = out.split(rule.from).join(rule.to);
  }
  return out;
}

/** 紧跟在 !/！/?/？ 之后不再补逗号的字符（已是标点/同类句末标点）。 */
const NO_COMMA_AFTER = new Set([",", "，", "、", "。", "；", ";", "：", ":", "!", "！", "?", "？", "…"]);

/** 感叹号 / 问号后补逗号：全角标点补「，」，半角标点补「,」（幂等）。 */
function insertCommaAfterPunct(text: string): string {
  const chars = Array.from(text);
  let out = "";
  for (let i = 0; i < chars.length; i += 1) {
    const ch = chars[i];
    out += ch;
    if (ch !== "!" && ch !== "！" && ch !== "?" && ch !== "？") continue;
    const next = chars[i + 1] ?? "";
    if (NO_COMMA_AFTER.has(next)) continue;
    out += ch === "！" || ch === "？" ? "，" : ",";
  }
  return out;
}

const HAN_OR_WORD = /[\p{Script=Han}A-Za-z0-9_]/u;

/** 在感叹词前插入前缀（前缀已紧邻则不重复插入）。 */
function prefixInterjections(text: string, prefix: string): string {
  let out = "";
  let prev = "";
  for (const ch of text) {
    const atBoundary = prev === "" || !HAN_OR_WORD.test(prev);
    if (INTERJECTIONS.includes(ch) && atBoundary && !out.endsWith(prefix)) {
      out += prefix;
    }
    out += ch;
    prev = ch;
  }
  return out;
}

/**
 * 对单个分段文本执行增强；顺序：感叹号/问号后补逗号 → 分词间隔 → 感叹词前缀。
 * 无有效选项时原样返回，保证幂等（同一文本重复执行结果一致）。
 */
export function enhanceIndexttsText(
  text: string,
  options: TextEnhanceOptions = { interjectionPrefix: DEFAULT_INTERJECTION_PREFIX }
): string {
  if (!text || !hasEnhancement(options)) return text;
  let out = text;
  if (options.entities?.length) out = applyEntityReplacements(out, options.entities);
  if (options.commaAfterPunct) out = insertCommaAfterPunct(out);
  if (options.wordGap) {
    const gap = options.wordGap;
    // 过滤掉上一步插入的间隔符，保证重复执行结果一致（幂等）。
    out = cutWords(out)
      .filter((word) => word !== gap)
      .join(gap);
  }
  if (options.interjectionPrefix) out = prefixInterjections(out, options.interjectionPrefix);
  return out;
}
