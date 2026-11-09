"""questions_md_vi: the Vietnamese wording `harness questions-md` prints for each question code.

PROPOSED engineer-facing copy, pending engineer review. Nothing here is approved wording: the engineer
(or whoever owns the Vietnamese copy) reviews and corrects it, and a code without a row here is rendered
with its English `message` verbatim and listed in the command's `untranslated_codes`.

One row per code a question producer can raise today (`intake`, `read-structure`, `callouts`,
`grid-system`; the producers' codes are listed in ask.OTHER_OWNERS). Row = (topic, need_vi, impact_vi):

  topic       one of TOPICS (the order of TOPICS is the order of the headings in questions.md)
  need_vi     "Cần gì": what the engineer has to tell us or decide
  impact_vi   "Ảnh hưởng": what depends on the answer

Plain short Vietnamese: "bản vẽ", "lưới trục", "tờ" instead of tool jargon. Codes, ids, file names,
`found` / `where` strings and commands are never translated.
"""

from __future__ import annotations

# (slug, heading) in the order questions.md prints them
TOPICS: tuple[tuple[str, str], ...] = (
    ("units", "Đơn vị bản vẽ"),
    ("convert", "Chuyển đổi và đọc file"),
    ("fonts", "Phông chữ / mã hoá"),
    ("sheets", "Tờ bản vẽ"),
    ("grids", "Lưới trục và hệ lưới"),
    ("levels", "Cao độ"),
    ("marks", "Ký hiệu và cấu kiện"),
    ("schedules", "Bảng thống kê"),
    ("reader", "Câu hỏi của người đọc (reader)"),
    ("other", "Khác"),
)
TOPIC_TITLE = dict(TOPICS)

# grid_system_missing: the second way to answer (ADR-0013 §2, no_grid=yes alone), printed under the command
NO_GRID_VI = (
    "Nếu file này không có mặt bằng cần lưới trục (chỉ có ghi chú, chi tiết hoặc mặt cắt), kỹ sư trả lời "
    "thay bằng"
)

# code -> (topic, need_vi, impact_vi)
CODES: dict[str, tuple[str, str, str]] = {
    # --- units ---
    "units_confirm_all": (
        "units",
        "Xác nhận đơn vị vẽ của file này (mm, cm, m, in hoặc ft). Đơn vị khai trong header của file "
        "không được tin tự động; đối chiếu với một kích thước đã biết, một bản PDF hoặc hiểu biết của bạn.",
        "Mọi toạ độ, khoảng cách lưới trục và chiều dài cấu kiện của file này.",
    ),
    "units_confirm": (
        "units",
        "Xác nhận đơn vị khai trong header của file này (câu này đã được gộp vào câu xác nhận đơn vị "
        "của cả file).",
        "Mọi toạ độ và chiều dài đọc từ file này.",
    ),
    "units_conflict": (
        "units",
        "Đơn vị khai trong header ($INSUNITS) và hệ đo của header ($MEASUREMENT) mâu thuẫn nhau. "
        "Cho biết toạ độ của file được vẽ bằng đơn vị nào.",
        "Mọi toạ độ, khoảng cách lưới trục và chiều dài cấu kiện của file này.",
    ),
    "units_suspect": (
        "units",
        "Với đơn vị khai trong header, kích thước dài điển hình ra giá trị không hợp lý cho một công trình. "
        "Cho biết đơn vị khai trong header có đúng không, hoặc đơn vị thật là gì.",
        "Mọi toạ độ, khoảng cách lưới trục và chiều dài cấu kiện của file này.",
    ),
    "units_unknown": (
        "units",
        "Header của file không cho đơn vị dùng được (thiếu, bằng 0, không hợp lệ hoặc ngoài mm/cm/m/in/ft). "
        "Cho biết toạ độ được vẽ bằng đơn vị nào; không tự giả định là mét.",
        "Mọi toạ độ, khoảng cách lưới trục và chiều dài cấu kiện của file này.",
    ),
    "grid_units_doubt": (
        "units",
        "Với đơn vị khai trong header, khoảng cách giữa các lưới trục không hợp lý cho một công trình "
        "(hoặc file không khai đơn vị). Cho biết toạ độ của file được vẽ bằng đơn vị nào.",
        "Khoảng cách lưới trục của file này và mọi thứ tính từ lưới.",
    ),
    "units_answer_contradicts_evidence": (
        "units",
        "Đơn vị đã trả lời cho file này làm các kích thước trong bản vẽ ra giá trị không hợp lý cho một "
        "công trình. Nếu đơn vị đã trả lời đúng, xác nhận lại bằng chính đơn vị đó; nếu sai, trả lời lại "
        "câu xác nhận đơn vị của file (units_confirm_all) bằng đơn vị đúng.",
        "Mọi toạ độ, khoảng cách lưới trục và chiều dài cấu kiện của file này.",
    ),
    # --- converting and reading files ---
    "conversion_empty": (
        "convert",
        "File DWG đổi sang DXF mà không có đối tượng nào dù file không nhỏ. Xác nhận bản vẽ này thật sự "
        "trống, nếu không thì gửi bản xuất DXF hoặc PDF của tờ này. Khi chưa xác nhận, coi như đọc hỏng.",
        "Không lấy được gì từ file này.",
    ),
    "converter_errors": (
        "convert",
        "Bộ chuyển DWG in ra các dòng ERROR dù chạy xong: một số đối tượng hoặc chuỗi chữ có thể thiếu hoặc "
        "bị cụt. Kiểm tra các phần nhiều chữ của tờ, hoặc gửi bản xuất DXF hoặc PDF.",
        "Độ tin cậy của chữ và đối tượng đọc từ file này bị hạ.",
    ),
    "read_failed": (
        "convert",
        "Không cách đọc nào hiện có đọc được file này. Gửi bản xuất DXF hoặc PDF của tờ.",
        "Không có dữ liệu nào từ file này.",
    ),
    "no_reader_implemented": (
        "convert",
        "Chưa có bộ đọc cho định dạng file này nên chưa lấy được gì. Gửi bản DXF hoặc DWG của từng tờ, "
        "hoặc chờ có bộ đọc.",
        "Không có dữ liệu nào từ các file này.",
    ),
    "file_set_relation": (
        "convert",
        "Cho biết những file bản vẽ nào thuộc cùng một bộ (cùng một công trình, cùng một hệ lưới trục). "
        "Mỗi file nằm trong đúng một bộ, ví dụ --value set1=a.dwg,b.dwg --value set2=c.dwg.",
        "Lưới trục chỉ được so sánh giữa các file cùng bộ; trước khi trả lời, xung đột lưới giữa các file "
        "chưa chặn nhưng còn chờ câu này.",
    ),
    "xref_unresolved": (
        "convert",
        "Không tìm thấy file tham chiếu ngoài (xref). Gửi file được tham chiếu, hoặc xác nhận bản vẽ đã đủ "
        "mà không cần nó.",
        "Phần bản vẽ nằm trong file tham chiếu bị thiếu.",
    ),
    "unreadable_objects": (
        "convert",
        "Một số đối tượng trong file không đọc được nên không có trong dữ liệu. Nếu chúng quan trọng, gửi "
        "bản PDF hoặc DXF đã đơn giản hoá.",
        "Những đối tượng đó vắng mặt trong mọi kết quả đọc.",
    ),
    "probe_section_failed": (
        "convert",
        "Bước khảo sát file không tính được một phần dữ liệu; không được dựa vào phần đó. Đây là lỗi của "
        "công cụ: báo lỗi và đọc bản vẽ bằng cách khác.",
        "Phần dữ liệu đó của file không dùng được.",
    ),
    "dimension_override_differs": (
        "convert",
        "Chữ kích thước bị gõ đè và khác với giá trị đo từ hình vẽ. Giá trị nào đúng: chữ hay hình?",
        "Các kích thước và khoảng cách lấy từ những kích thước này.",
    ),
    "multiple_scales": (
        "convert",
        "File dùng nhiều hơn một tỷ lệ (tỷ lệ kích thước hoặc tỷ lệ khung nhìn). Tỷ lệ nào áp dụng cho "
        "phần nào của bản vẽ?",
        "Kích thước đọc từ các phần dùng tỷ lệ khác nhau.",
    ),
    # --- fonts and encodings ---
    "text_encoding_hint": (
        "fonts",
        "Một kiểu chữ có vẻ dùng phông tiếng Việt cũ. Chữ trong kiểu này có thể cần chuyển mã. Đây chỉ là "
        "gợi ý, chưa phải kết luận; không cần làm gì nếu bạn đã biết.",
        "Tên tờ, ghi chú và ký hiệu viết bằng kiểu chữ này.",
    ),
    "font_encoding_proposed": (
        "fonts",
        "Một kiểu chữ khớp với dòng ĐỀ XUẤT trong bảng mã phông (knowledge/font-encodings.csv). Dòng đề "
        "xuất chưa có tác dụng: chữ vẫn bị coi là chưa biết mã. Xem bằng chứng rồi duyệt hoặc bác dòng đó.",
        "Chữ tiếng Việt trong kiểu này chưa đọc đúng cho đến khi dòng được duyệt.",
    ),
    "font_encoding_conflict": (
        "fonts",
        "Một kiểu chữ khớp nhiều dòng đã duyệt của bảng mã phông mà các dòng đó mâu thuẫn nhau về mã. "
        "Chưa giải mã gì cho kiểu này. Sửa hoặc bác một trong các dòng.",
        "Chữ tiếng Việt trong kiểu này chưa đọc được.",
    ),
    "encoding_unknown_non_ascii": (
        "fonts",
        "Có chữ không phải ASCII trong kiểu chữ mà tên phông không cho biết mã. Chữ được giữ nguyên như "
        "lưu, độ tin cậy thấp. Cho biết mỗi kiểu chữ dùng mã nào (TCVN3, VNI hay Unicode); câu trả lời có "
        "thể trở thành một dòng đã duyệt trong knowledge/font-encodings.csv.",
        "Tên tờ, ghi chú, ký hiệu cấu kiện và bảng viết bằng các kiểu chữ này có thể đọc sai.",
    ),
    "legacy_ascii_text": (
        "fonts",
        "Kiểu chữ này dùng phông tiếng Việt cũ nhưng chữ lưu trong file chỉ gồm ký tự ASCII, nên chưa biết "
        "chữ hiển thị là gì (ví dụ ghi chú thép trên chi tiết dầm, cột). Mở bản vẽ, xem vài chữ ví dụ "
        "(mã chữ T… ở mục Đã thấy) và cho biết kiểu chữ này chứa gì và có đọc được không. Câu trả lời chỉ "
        "ghi lại cách bạn đọc kiểu chữ đó; không chuyển mã gì.",
        "Mọi chữ của kiểu này vẫn bị chặn (không được dùng làm giá trị) cho đến khi có cách đọc được duyệt.",
    ),
    # --- sheets ---
    "sheets_not_detected": (
        "sheets",
        "Không tìm thấy khung tờ hay layout giấy có nội dung, nên mọi giá trị ghi tờ là 'unknown'. File "
        "này được chia thành các tờ như thế nào?",
        "Mọi giá trị đọc từ file này không gắn được với tờ nào.",
    ),
    "sheet_number_missing": (
        "sheets",
        "Không gắn được số hiệu tờ vào ô khung tên của các tờ này. Cho biết số hiệu in trên từng tờ.",
        "Danh sách tờ và nguồn gốc (tờ nào) của mọi giá trị.",
    ),
    "revision_missing": (
        "sheets",
        "Không gắn được lần sửa đổi (revision) vào ô khung tên của các tờ này (hỏi một lần cho cả bộ). "
        "Lần sửa đổi hiện hành là gì?",
        "Biết bản vẽ nào còn hiệu lực.",
    ),
    "texts_unassigned": (
        "sheets",
        "Một số chữ nằm ngoài mọi tờ đã nhận ra (ghi chú, nháp, hoặc một tờ chưa nhận ra). Chúng có thuộc "
        "bộ bản vẽ không?",
        "Những chữ đó chưa được dùng để đọc ghi chú, ký hiệu hay bảng.",
    ),
    "texts_ambiguous_sheet": (
        "sheets",
        "Một số chữ trong không gian mô hình được khung nhìn của nhiều tờ cùng hiển thị nên chưa gán vào "
        "tờ nào.",
        "Những chữ đó chưa gắn được với một tờ.",
    ),
    "sheet_frames_overlap": (
        "sheets",
        "Hai khung tờ chồng lên nhau; khung lớn hơn được dùng, khung kia bị bỏ. Khung nào là tờ thật?",
        "Danh sách tờ và các giá trị gắn với từng tờ.",
    ),
    "sheet_frame_ambiguous": (
        "sheets",
        "Một khung hình tờ chứa nhiều khung hình tờ khác không có khung tên riêng: hiện giữ là MỘT tờ (các "
        "khung bên trong là khung nhìn). Các khung bên trong có phải là các tờ riêng không?",
        "Danh sách tờ và các giá trị gắn với từng tờ.",
    ),
    "sheet_frame_candidates_rejected": (
        "sheets",
        "Có nhóm hình chữ nhật cùng cỡ chứa chữ nhưng không đúng tỷ lệ hoặc kích thước của một tờ. Có cái "
        "nào là khung tờ không?",
        "Có thể còn tờ chưa được nhận ra.",
    ),
    "sheet_number_gap": (
        "sheets",
        "Dãy số hiệu tờ của file này bị hụt (ví dụ có KC-24 và KC-26 nhưng không có KC-25). Xem các số "
        "còn thiếu và các tờ hai bên ở mục Đã thấy: tờ đó bị thiếu trong bộ, đánh số nhảy có chủ ý, hay "
        "số hiệu bị đọc sai?",
        "Biết bộ bản vẽ đã đủ tờ chưa.",
    ),
    "sheet_number_duplicate": (
        "sheets",
        "Nhiều tờ mang cùng một số hiệu (hai lần sửa, một bản sao, hoặc đọc nhầm). Tờ nào là bản hiện hành?",
        "Chọn tờ nào để đọc khi hai tờ trùng số hiệu.",
    ),
    "sheet_content_duplicate": (
        "sheets",
        "Các tờ này có đúng cùng một nội dung chữ (bản sao của tờ, ví dụ nằm trong block, hoặc hai lần "
        "sửa). Tờ nào là bản vẽ cần đọc?",
        "Tránh đọc trùng; chọn đúng bản hiện hành.",
    ),
    "title_field_conflict": (
        "sheets",
        "Khung tên đưa ra nhiều giá trị khác nhau cho cùng một ô (chưa chọn giá trị nào). Giá trị nào được "
        "in trên tờ này?",
        "Số hiệu tờ hoặc lần sửa đổi của tờ này.",
    ),
    # --- grids ---
    "grid_none_found": (
        "grids",
        "Không tìm thấy lưới trục nào (cần ít nhất hai trục có nhãn). Lưới trục được định nghĩa ở đâu?",
        "Không dựng được lưới trục; toạ độ cấu kiện không có hệ quy chiếu.",
    ),
    "grid_family_axis_assignment": (
        "grids",
        "Họ lưới trục nào là trục X của Tekla (các đường song song với Y) và họ nào là Y? Hướng của từng họ "
        "ghi ở mục Đã thấy. (Hướng X/Y của cả hệ lưới được hỏi ở câu grid_system_axis_unassigned.)",
        "Hướng X/Y của lưới trong Tekla.",
    ),
    "grid_gate1_confirmation": (
        "grids",
        "Cổng 1: xác nhận các họ lưới trục, nhãn, khoảng cách và chuỗi toạ độ đề xuất.",
        "Lưới trục dựng trong Tekla.",
    ),
    "grid_label_duplicate": (
        "grids",
        "Cùng một nhãn trục xuất hiện ở các vị trí khác nhau trong một hình. Vị trí nào đúng?",
        "Nhãn và khoảng cách của lưới trục.",
    ),
    "grid_label_missing": (
        "grids",
        "Một đường lưới kết thúc ở bong bóng trống: thiếu nhãn. Nhãn của trục là gì (hay đó không phải "
        "là trục)?",
        "Nhãn và khoảng cách của lưới trục.",
    ),
    "grid_axis_unlabelled": (
        "grids",
        "Một đường nằm trên layer và kiểu đường của lưới trục, trông như một trục nữa nhưng không có bong "
        "bóng. Có phải là trục lưới không, và nhãn là gì?",
        "Số trục và khoảng cách của lưới trục.",
    ),
    "grid_axis_label_conflict": (
        "grids",
        "Một đường lưới mang các bong bóng khác nhãn, hoặc hai trục khác nhãn nằm trên cùng một đường. "
        "Nhãn nào đúng?",
        "Nhãn của lưới trục.",
    ),
    "grid_axis_layer_mismatch": (
        "grids",
        "Các trục của họ này vẽ trên layer hoặc kiểu đường khác nhau; có thể đã nhận nhầm một đường khác "
        "(đường cắt, đường tường) là trục. Đường nào là trục lưới?",
        "Số trục và khoảng cách của lưới trục.",
    ),
    "grid_axis_not_parallel": (
        "grids",
        "Trục này không song song với các trục còn lại của họ nên khoảng cách đổi dọc theo trục. Trục thật "
        "sự bị xiên, hay bản vẽ không chính xác?",
        "Khoảng cách của lưới trục.",
    ),
    "grid_axis_skewed": (
        "grids",
        "Một trục cắt hình ở góc không song song cũng không vuông góc với các trục khác. Đó có phải đường "
        "lưới xiên không (Tekla cần một lưới hoặc đường riêng)?",
        "Cách dựng lưới trục trong Tekla.",
    ),
    "grid_two_bubble_axis": (
        "grids",
        "Hai bong bóng cùng nhãn đối diện nhau không có đường lưới ở giữa; trục được giả định chạy giữa hai "
        "tâm bong bóng. Giả định đó có đúng không?",
        "Vị trí của trục này.",
    ),
    "grid_label_kind_mixed": (
        "grids",
        "Nhãn số và nhãn chữ lẫn trong một họ (số chạy một hướng, chữ chạy hướng kia); có thể một bong bóng "
        "thuộc thứ khác (ký hiệu, chi tiết). Nhãn nào là trục lưới?",
        "Nhãn và số trục của lưới.",
    ),
    "grid_label_order_nonmonotonic": (
        "grids",
        "Nhãn trục của họ này không chạy theo một chiều (ví dụ 1 3 2 4): có nhãn đặt sai hoặc bong bóng "
        "thuộc đường khác. Thứ tự nào đúng?",
        "Nhãn và khoảng cách của lưới trục.",
    ),
    "grid_label_sequence_gap": (
        "grids",
        "Nhãn trục bỏ qua một giá trị trong họ này (chữ I và O thường bị bỏ; quy ước này chưa được kiểm "
        "chứng). Bản vẽ có thiếu trục không?",
        "Số trục của lưới.",
    ),
    "grid_label_order_mismatch": (
        "grids",
        "Cùng các nhãn trục nhưng thứ tự khác nhau ở hai hình. Thứ tự nào đúng?",
        "Nhãn và khoảng cách của lưới trục.",
    ),
    "grid_rotated": (
        "grids",
        "Họ lưới này xoay so với các trục của tờ. Xác nhận góc xoay (Tekla cần góc này làm mặt phẳng làm "
        "việc hoặc góc xoay gốc của lưới).",
        "Hướng của lưới trong Tekla.",
    ),
    "grid_non_orthogonal": (
        "grids",
        "Hai họ lưới trong một hình không vuông góc; lưới chữ nhật của Tekla không biểu diễn được. Nên mô "
        "hình hoá lưới này thế nào?",
        "Cách dựng lưới trục trong Tekla.",
    ),
    "grid_dimension_override_mismatch": (
        "grids",
        "Một kích thước giữa các trục lưới ghi giá trị khác với khoảng cách trục đã vẽ (chữ bị gõ đè). Giá "
        "trị nào đúng?",
        "Khoảng cách của lưới trục.",
    ),
    "grid_scale_differs": (
        "grids",
        "Hai hình cho cùng các trục với mọi khoảng cách theo một tỷ lệ không đổi (có hình vẽ ở tỷ lệ khác?). "
        "Hình nào có lưới đúng kích thước?",
        "Khoảng cách của lưới trục.",
    ),
    "grid_spacing_cross_sheet_mismatch": (
        "grids",
        "Cùng các trục nhưng khoảng cách khác nhau ở hai hình. Khoảng cách nào đúng?",
        "Khoảng cách của lưới trục.",
    ),
    "grid_spacing_drafting_tolerance": (
        "grids",
        "Cùng các trục lệch nhau rất ít giữa hai hình (có thể do vẽ không chính xác). Giá trị nào là ý định "
        "của thiết kế?",
        "Khoảng cách của lưới trục (sai khác nhỏ).",
    ),
    "grid_system_select": (
        "grids",
        "Cổng 1: trong các hệ lưới được liệt kê, hệ nào là lưới của dự án, và mỗi hệ là toà nhà hoặc kết "
        "cấu nào? Chưa xác nhận thì chưa hệ nào được dùng. Ghi lời trả lời; có thể thêm --value "
        "systems=S001,S002 (các hệ dự án dùng, hệ còn lại hết chặn) và --value separate=S001,S002 (các hệ "
        "đã chọn mà là toà nhà khác nhau: đóng xung đột giữa chúng).",
        "Lưới trục dùng để dựng mô hình; mọi toạ độ cấu kiện tính theo lưới này.",
    ),
    "grid_system_conflict": (
        "grids",
        "Hai hệ lưới dùng cùng nhãn trục nhưng khoảng cách hoặc thứ tự khác nhau nên được tách riêng. Là "
        "hai toà nhà hoặc kết cấu khác nhau, hay một trong hai hệ sai? Câu này chỉ đóng qua câu trả lời "
        "grid_system_select (xem Cách đóng); trả lời bằng lời ở đây không đóng được gì.",
        "Chọn hệ lưới nào dùng để dựng.",
    ),
    "grid_system_units_unconfirmed": (
        "grids",
        "Hệ lưới này tính theo đơn vị bản vẽ vì chưa có câu trả lời đơn vị thống nhất cho mọi file tạo nên "
        "nó. Trả lời câu xác nhận đơn vị (units_confirm_all) của từng file liên quan rồi chạy lại lệnh "
        "grid-system; câu này không nhận giá trị.",
        "Khoảng cách của hệ lưới đổi sang mm.",
    ),
    "grid_system_axis_unassigned": (
        "grids",
        "Hướng nào của hệ lưới này là trục X của Tekla (các đường song song với Y) và hướng nào là Y? Cho X "
        "hoặc Y cho từng hướng (dir1, dir2: xem mục Chủ đề và mục Đã thấy); hai hướng không được cùng một "
        "trục. Sau đó chạy lại lệnh grid-system.",
        "Hướng X/Y của lưới trong Tekla.",
    ),
    "grid_system_missing": (
        "grids",
        "Cổng 1: file này có mặt bằng nhưng công cụ không tìm được hệ lưới trục dùng được (cần ít nhất hai "
        "trục có nhãn ở mỗi phương). Những gì đã tìm thấy (bóng trục, nhãn, hệ bị loại) ở mục Đã thấy. Đọc "
        "lưới trục trên bản vẽ và cho nhãn cùng khoảng cách của cả hai phương, theo đơn vị bản vẽ, theo "
        "thứ tự trên bản vẽ: --value dir1_labels=1,2,3 --value dir1_spacings=3130,3540 --value "
        "dir2_labels=A,B --value dir2_spacings=4250 (mỗi phương có số khoảng cách ít hơn số nhãn một); "
        "thêm --value sheet=model#05 nếu đọc từ một tờ cụ thể. Nếu file không có mặt bằng cần lưới trục "
        "(chỉ có ghi chú, chi tiết hoặc mặt cắt) thì trả lời riêng --value no_grid=yes. Chỉ câu trả lời "
        "của kỹ sư (--role engineer) mới tạo được hệ lưới hoặc đóng được câu này; sau đó chạy lại lệnh "
        "grid-system.",
        "Lưới trục của file này; không có nó thì cổng 1 không mở được.",
    ),
    "grid_answer_contradicts_drawing": (
        "grids",
        "Khoảng cách lưới trục kỹ sư đã cho khác với kích thước vẽ giữa hai trục đó trên bản vẽ (cả hai giá "
        "trị ở mục Đã thấy). Kiểm tra lại: sửa câu trả lời grid_system_missing nếu nhập sai, hoặc xác nhận "
        "câu trả lời là đúng (bản vẽ ghi sai). Câu này không nhận giá trị.",
        "Khoảng cách lưới trục dùng để dựng mô hình.",
    ),
    # --- levels ---
    "level_storey_selection": (
        "levels",
        "Chưa biết chắc cao độ nào là sàn tầng: hoặc có ít hơn hai cao độ gắn được với tên tầng, hoặc có "
        "cao độ mang chữ chỉ tầng nhưng không có tên tầng nên chiều cao tầng đã tính bỏ qua nó (danh sách ở "
        "mục Đã thấy; bậc cửa, hố, bậc thềm cũng là cao độ). Cao độ nào là sàn tầng?",
        "Danh sách tầng và cao độ tầng của mô hình.",
    ),
    "level_none_found": (
        "levels",
        "Không tìm thấy chữ cao độ nào (giá trị có dấu theo mét như '+3.600'). Cao độ được cho ở đâu?",
        "Cao độ tầng của mô hình.",
    ),
    "level_finished_vs_structural": (
        "levels",
        "Các cao độ này là cao độ hoàn thiện hay cao độ kết cấu (mặt sàn, mặt dầm)? Quy ước chưa được kiểm "
        "chứng và hai loại khác nhau một bề dày lớp vữa.",
        "Cao độ đặt cấu kiện theo phương đứng.",
    ),
    "level_datum_not_found": (
        "levels",
        "Không tìm thấy cao độ chuẩn ±0.000 trong các cao độ. Cao độ chuẩn của dự án là gì?",
        "Gốc cao độ của mô hình.",
    ),
    "level_decimals_nonstandard": (
        "levels",
        "Một số cao độ ghi ít hơn ba chữ số thập phân; xác nhận chúng tính bằng mét.",
        "Giá trị cao độ.",
    ),
    "level_name_conflict": (
        "levels",
        "Cùng một tên tầng nhưng cho cao độ khác nhau. Cao độ nào đúng (hay là các cao độ chuẩn khác nhau, "
        "ví dụ kiến trúc và kết cấu)?",
        "Cao độ tầng của mô hình.",
    ),
    "level_value_out_of_range": (
        "levels",
        "Một giá trị cao độ nằm ngoài khoảng -50 m đến +300 m: nó có phải ở đơn vị khác (mm?) hay không "
        "phải cao độ?",
        "Giá trị cao độ đó.",
    ),
    "level_negative_storey": (
        "levels",
        "Tên tầng được viết cùng cao độ âm: là tầng hầm, hay dấu gạch chỉ là ký tự ngăn cách ('TẦNG 2 "
        "-3.600' nghĩa là +3.600)? Là trường hợp nào?",
        "Cao độ của tầng đó.",
    ),
    "level_single_occurrence": (
        "levels",
        "Cao độ này chỉ xuất hiện một lần trong file (tờ sao chép không tính), chưa được hình nào khác đối "
        "chiếu. Xác nhận cao độ đúng.",
        "Độ tin cậy của cao độ đó.",
    ),
    # --- marks and members ---
    "callout_ambiguous": (
        "marks",
        "Một số chữ ghi chú khớp một cách ghi có hơn một nghĩa. Mỗi cách ghi (xem mục Chủ đề) là một câu "
        "hỏi riêng; câu hỏi của từng cách ghi nằm ở chỗ đầu tiên của nó. Trả lời bằng lời, theo từng "
        "cách ghi.",
        "Thép, kích thước hoặc ký hiệu đọc từ các ghi chú đó.",
    ),
    "callout_unparsed": (
        "marks",
        "Một số ghi chú thép, thép hình, bản mã hoặc bu lông trong file này giống một cách ghi nhưng không "
        "đọc được thành giá trị (mỗi câu là một nhóm lý do, xem mục Đã thấy: số lượng, 5 chữ ví dụ và các "
        "tờ). Ví dụ một ký tự lạ đứng ở chỗ ký hiệu đường kính Ø. Xem các chữ ví dụ trên bản vẽ và cho biết "
        "cách ghi đó nghĩa là gì, hoặc chúng có cần đọc không.",
        "Thép và cấu kiện ghi bằng các ghi chú đó chưa đưa được vào lô dựng mô hình.",
    ),
    "grade_legacy_mapping": (
        "marks",
        "Bản vẽ dùng nhóm thép cũ (CI..CIV, A-I..A-IV, AI..AIII). Nhãn này không cho cường độ chảy hay tiêu "
        "chuẩn sản phẩm, và không có quy đổi chính thức sang các mác CB. Trong dự án này mỗi nhóm nghĩa là "
        "mác, cường độ chảy và tiêu chuẩn nào?",
        "Mác thép của mọi thanh thép dùng nhóm cũ.",
    ),
    "member_mark_prefix_meaning": (
        "marks",
        "Mỗi tiền tố ký hiệu cấu kiện trong mục Chủ đề nghĩa là gì trong dự án này (cột, dầm, sàn, móng, "
        "giằng, thép hình...)? Không có tiêu chuẩn nào quy định các chữ cái; dùng bảng chú giải hoặc bảng "
        "thống kê cấu kiện. Trả lời mỗi tiền tố một giá trị.",
        "Loại cấu kiện của mọi ký hiệu mang tiền tố đó.",
    ),
    "mark_notation_equivalence": (
        "marks",
        "Cùng một cấu kiện có thể đang được ghi theo nhiều cách (ví dụ D1.1 và D1-1, C-01 và C1). Với "
        "từng nhóm trong mục Chủ đề, cho biết các cách ghi đó có phải là một cấu kiện không. Chưa trả lời "
        "thì không ghép chúng với nhau.",
        "Việc khớp ký hiệu trên mặt bằng với bảng thống kê, và số cấu kiện đếm được.",
    ),
    "mark_size_conflict": (
        "marks",
        "Kích thước ghi cạnh ký hiệu trên mặt bằng khác với kích thước trong bảng thống kê của cùng ký "
        "hiệu. Cho biết kích thước nào đúng (xem hai chỗ được trích).",
        "Tiết diện của cấu kiện mang ký hiệu đó.",
    ),
    "schedule_table_unparsed": (
        "schedules",
        "Có một bảng có tiêu đề cột giống bảng thống kê nhưng không đọc được thành các hàng. Kiểm tra bảng "
        "ở tờ và vị trí đã nêu; nếu là bảng thống kê cấu kiện, cho biết có cần đọc nó không.",
        "Các ký hiệu trong bảng đó chưa được khớp với mặt bằng.",
    ),
}

# code prefix -> topic, for codes without a row (a new producer code); first match wins
PREFIX_TOPICS: tuple[tuple[str, str], ...] = (
    ("units_", "units"),
    ("grid_", "grids"),
    ("level_", "levels"),
    ("sheet_", "sheets"),
    ("title_", "sheets"),
    ("font_", "fonts"),
    ("encoding_", "fonts"),
    ("callout_", "marks"),
    ("mark_", "marks"),
    ("member_", "marks"),
    ("rebar_", "marks"),
    ("steel_", "marks"),
    ("schedule_", "schedules"),
)
# registry producer -> topic, the last resort for a code without a row or a known prefix
PRODUCER_TOPICS = {
    "intake": "convert",
    "structure": "sheets",
    "callouts": "marks",
    "marks": "marks",
    "grid-system": "grids",
    "reader": "reader",
}


def topic_of(code: str, producer: str | None) -> str:
    """Topic slug of a question. A reader question is always in the reader topic."""
    if producer == "reader":
        return "reader"
    row = CODES.get(code)
    if row is not None:
        return row[0]
    for prefix, topic in PREFIX_TOPICS:
        if code.startswith(prefix):
            return topic
    return PRODUCER_TOPICS.get(producer or "", "other")
