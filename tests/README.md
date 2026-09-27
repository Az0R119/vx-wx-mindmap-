# 回归测试

改 parser / rules / render / worker 之后，跑一遍确认没把原来能用的搞坏。

```bash
unset PYTHONPATH && ./.venv/Scripts/python.exe tests/test_wxmindmap.py
```

要 6 个用例全绿。用例数据是真实微信导出 zip，不在仓库里：
默认找 `~/Desktop/05微信导出/`，别处就用环境变量：

```bash
WXM_TEST_DIR="D:/某处/05微信导出" ./.venv/Scripts/python.exe tests/test_wxmindmap.py
```

数据缺失或没装 node → 对应用例自动 skip（不算失败）。

## 覆盖什么

| 用例 | 挡的是什么 |
|------|-----------|
| test_old_format / test_new_format | 改 parser 时把另一种导出格式改坏 |
| test_transcripts | 喂 AI 的行生成崩掉 |
| test_new_format_renders | 免费版出图中途崩 |
| test_div_balanced | HTML 标签不平衡（历史高发 bug） |
| test_buckets_merge_synonyms | worker 归桶不再合并同义说法 |

## 现在没覆盖

AI 版（`render_ai.py`）、压缩、GUI。等真在这些地方出过"改 A 崩 B"再加。
