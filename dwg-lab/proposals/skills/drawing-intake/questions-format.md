# `questions.md` format

The single question format for every skill. `work/*questions.json` and
`work/question-registry.json` are the source of truth; `questions.md` is the engineer's view of
them. Keys and codes English, prose Vietnamese with full diacritics.

```markdown
## Q-003 · units_confirm_all · CHẶN

- **File:** `dwgshare-rc-projects/267.dwg` · **tờ:** chưa xác định
- **Cần gì:** xác nhận đơn vị vẽ của file này.
- **Đã thấy (nguyên văn):** `m ($INSUNITS=6), confidence low, flags: units_conflict, units_suspect`
- **Bằng chứng thêm:** lưới `1 2 3 4 5` = `0 5580 4660 3920 2720` (đơn vị bản vẽ)
- **Ảnh hưởng:** mọi toạ độ, lưới trục, chiều dài cấu kiện của file này.
- **Số chỗ:** 1 (đầy đủ) · **Nguồn:** `work/questions.json` · key `be71438bccbc105c`
- **Trả lời:** _chưa có_
```

Rules:

- Id, code, key and file come from the JSON; you never invent or renumber ids.
- Quote what was found verbatim in code format; never paraphrase a drawing value.
- `count` and `truncated` are printed. A truncated question says how many places exist and
  points to the JSON for the full list; it shows at most 10 refs.
- One question asks one thing; the JSON already splits by code and file.
- A suggestion is labelled `Đề xuất (chưa xác nhận)` and never written as the answer.
- **Trả lời** shows the active answer from `work/answers.json` (text, by, date) or `chưa có`.
  The answer itself is recorded only with `harness answer`; editing `questions.md` records nothing.
