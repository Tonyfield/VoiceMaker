import assert from "node:assert/strict";
import test from "node:test";
import { enhanceIndexttsText, enhanceOptionsFromParams } from "./indexttsText";

test("感叹词前插入中杠（串首/标点边界）", () => {
  assert.equal(enhanceIndexttsText("啊，原来是你"), "-啊，原来是你");
  assert.equal(enhanceIndexttsText("哦！"), "-哦！");
  assert.equal(enhanceIndexttsText("他说：呀，是你"), "他说：-呀，是你");
});

test("语气助词（前面是汉字）不插入", () => {
  assert.equal(enhanceIndexttsText("好呀"), "好呀");
  assert.equal(enhanceIndexttsText("你来啊"), "你来啊");
});

test("已插入过不重复；空串原样返回", () => {
  assert.equal(enhanceIndexttsText("-啊，好"), "-啊，好");
  assert.equal(enhanceIndexttsText(""), "");
});

test("连续感叹词逐个处理", () => {
  assert.equal(enhanceIndexttsText("啊，哦，呀"), "-啊，-哦，-呀");
});

test("非感叹词汉字不受影响", () => {
  assert.equal(enhanceIndexttsText("阿房宫赋"), "阿房宫赋");
});

test("可配置感叹词前缀（含幂等）", () => {
  assert.equal(enhanceIndexttsText("啊，好", { interjectionPrefix: "~" }), "~啊，好");
  assert.equal(enhanceIndexttsText("~啊，好", { interjectionPrefix: "~" }), "~啊，好");
  // 关闭前缀（空字符串）时不处理
  assert.equal(enhanceIndexttsText("啊，好", { interjectionPrefix: "" }), "啊，好");
});

test("在每个分词之间插入填充字符串（含幂等）", () => {
  const out = enhanceIndexttsText("我们来测试一下", { wordGap: "|" });
  assert.ok(out.includes("|"));
  assert.equal(enhanceIndexttsText(out, { wordGap: "|" }), out);
});

test("两项同时开启：先分词间隔、再感叹词前缀", () => {
  const out = enhanceIndexttsText("啊，我们走", { interjectionPrefix: "-", wordGap: "|" });
  assert.ok(out.startsWith("-啊"));
  assert.ok(out.includes("|"));
});

test("专有名词替换：按替换文本改写且幂等", () => {
  const entities = [
    { from: "桑丘·潘沙", to: "“桑丘·潘沙”" },
    { from: "罗塔里奥", to: "罗塔里奥" },
  ];
  const out = enhanceIndexttsText("桑丘·潘沙对罗塔里奥说", { entities });
  assert.equal(out, "“桑丘·潘沙”对罗塔里奥说");
  // 已替换过的不再重复（幂等）
  assert.equal(enhanceIndexttsText(out, { entities }), out);
});

test("enhanceOptionsFromParams 读取复选框与字符", () => {
  // 未设置时，感叹词前缀默认开启并用默认中杠
  assert.deepEqual(enhanceOptionsFromParams({}), {
    interjectionPrefix: "-",
    wordGap: undefined,
    commaAfterPunct: false,
  });
  assert.deepEqual(enhanceOptionsFromParams({ interjection_prefix_enabled: false }), {
    interjectionPrefix: undefined,
    wordGap: undefined,
    commaAfterPunct: false,
  });
  assert.deepEqual(
    enhanceOptionsFromParams({
      word_gap_enabled: true,
      word_gap: "/",
      punct_comma_enabled: true,
    }),
    { interjectionPrefix: "-", wordGap: "/", commaAfterPunct: true }
  );
});

test("感叹号/问号后补逗号（全角补「，」、半角补「,」）", () => {
  assert.equal(
    enhanceIndexttsText("你好！你是谁？", { commaAfterPunct: true }),
    "你好！，你是谁？，"
  );
  assert.equal(
    enhanceIndexttsText("Hi! Are you ok?", { commaAfterPunct: true }),
    "Hi!, Are you ok?,"
  );
});

test("补逗号：后面已是逗号或同类标点则不重复插入，且幂等", () => {
  assert.equal(
    enhanceIndexttsText("你好！，真好", { commaAfterPunct: true }),
    "你好！，真好"
  );
  assert.equal(
    enhanceIndexttsText("什么？！", { commaAfterPunct: true }),
    "什么？！，"
  );
  const once = enhanceIndexttsText("真的吗？", { commaAfterPunct: true });
  assert.equal(once, "真的吗？，");
  assert.equal(enhanceIndexttsText(once, { commaAfterPunct: true }), once);
});
