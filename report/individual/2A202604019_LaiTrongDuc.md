# Báo cáo cá nhân — Data Ingestion

**Học viên:** LẠI TRỌNG ĐỨC · **MSSV:** 2A202604019 · **Lớp:** L3B

**Chủ đề:** Tra cứu kiến thức Python cơ bản cho học sinh, sinh viên.

**Nhánh triển khai:** `feat/data-ingestion` · **Nhánh phát hành:** `main` · **Ngày chạy:** 14/11/2026.

Đã chạy cùng corpus/model/pgvector cho A/B/C, lưu 60 trace và 180 bản ghi top-3. **B được chọn trên dev trước khi chạy test**, đạt Evidence Hit@3 dev 11/15 và test 3/5. C đạt cùng số hit nhưng bảo đảm phạm vi chapter cho các câu có filter. Không điều chỉnh cấu hình sau khi xem test.

Báo cáo và phân tích được Codex hỗ trợ. Các nhãn định tính dưới đây do **Codex đọc và đánh giá**, có lý do từng mẫu; **chưa có xác nhận chấm thủ công của học viên/người chấm độc lập**. Không trình bày chúng như nhãn do con người đã chấm. Số retrieval tự động và kết quả kiểm thử được chạy thật.

## Dữ liệu và pipeline

Nguồn là *Think Python: How to Think Like a Computer Scientist*, Allen B. Downey, 2nd Edition, Version 2.4.1, copyright 2015. [PDF gốc](https://greenteapress.com/thinkpython2/thinkpython2.pdf) có giấy phép **CC BY-NC 3.0 Unported**; xem trang bản quyền PDF vật lý 4 và [giấy phép](https://creativecommons.org/licenses/by-nc/3.0/). PDF giữ nguyên; text dẫn xuất được chọn/chuẩn hóa cho bài thực hành giáo dục phi thương mại, có ghi công trong [manifest](../../data/manifest.json). Truy cập lúc `2026-11-14T03:11:11Z`.

PDF có 244 trang vật lý. Chọn **40 trang nội dung**, không nhân bản: 31–36, 39–48, 61–68, 85–90, 111–115, 125–129, tương ứng chương 2, 3, 5, 7, 10, 11. Không tính bìa, mục lục, trang trống hoặc các trang ngoài phạm vi chọn. Các trang mở chương và glossary được tính vì có kiến thức hữu ích. Tổng **76.707 ký tự** sau chuẩn hóa; trang ngắn nhất 1.148 ký tự. `page` luôn là trang PDF vật lý, 1-based; `printed_page = page - 22` trong các phạm vi này.

SHA-256 PDF: `6033000bac3f9268ad75ee041bf8e5d9a3bc8a33bb156399cbd014918cb59f94`.

Python dùng pypdf xác minh cấu trúc/số trang, Poppler `pdftotext -layout` trích nội dung, chuẩn hóa Unicode NFC và xuống dòng, xóa running header có mẫu được kiểm chứng. Giữ indentation, dấu câu, toán tử và dấu nối cuối dòng để tránh làm hỏng code. Không OCR; phát hiện trang vật lý 2 không có text, ghi [log](../../results/ingestion_errors.jsonl), không đưa vào corpus. Thống kê tại [ingestion_stats.json](../../results/ingestion_stats.json); văn bản/metadata tại [pages.jsonl](../../data/processed/pages.jsonl).

Embedding local: **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`**, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, 384 chiều, CPU float32, batch 16, L2-normalized. Query/document encode text thuần, không prompt/title. Giữ max sequence length **128 token tính cả special tokens** theo [model card](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2). Chunk vượt hạn mức được chia tiếp bằng đúng tokenizer/revision; input embedding quá dài sẽ báo lỗi, không truncate âm thầm.

Store: **PostgreSQL 16.16 + pgvector 0.8.7**, cosine similarity `1 - (embedding <=> query)`, exact search, không ANN index. Dữ liệu trong volume Docker `pg_data`, bảng `day6_chunks`, khóa `(namespace, strategy, chunk_id)`. Namespace được tính từ cấu hình, corpus và phiên bản thư viện; lần chạy này có signature `6a10d47f60be99ad23235faca7c2cee88a06d30cb788fe9dccd6971af2f7d2ce`. A/B là hai phân vùng logic; C dùng B, không tạo thêm vector. Xem [cấu hình](../../starter/model_config.json) và [stats thực tế](../../results/vector_ingestion_stats.json).

Upsert snapshot và xóa ID lỗi thời diễn ra trong cùng transaction, giới hạn đúng namespace/strategy. Nạp lại A/B vẫn 244/229 bản ghi, không trùng; đóng/mở lại kết nối và CLI từ tiến trình mới giữ top-3/score. Đổi phiên bản tạo namespace khác để tách các lần chạy; namespace cũ không bị tự xóa. Kiểm thử thêm trường hợp cập nhật snapshot làm mất chunk cũ.

Metadata bắt buộc: `document_id:string`, `source:string`, `page:integer`. Trường lọc **`chapter:integer`** lấy từ heading/running header PDF và phạm vi đã kiểm chứng trong manifest; giúp giới hạn đúng chương người dùng yêu cầu. Có `chapter_title`, `version`, `language`, `page_id`, `printed_page`, `source_sha256`, `start_char/end_char` 0-based/end-exclusive để truy vết. Không suy diễn chapter từ gold khi truy vấn.

## Cấu hình và benchmark

| Cấu hình | Chunking | Retrieval |
|---|---|---|
| A | Cửa sổ 500 ký tự, overlap 50; chia thêm nếu vượt 128 token | Cùng metadata, không filter |
| B | Ghép theo đoạn, tối đa 500 ký tự; tách đoạn dài ở newline/space, chia thêm theo token | Cùng metadata, không filter |
| C | **Giống hệt B**, cùng IDs/text/vector | Áp dụng chapter có sẵn trong câu hỏi; không có thì không filter |

A–B chỉ đổi cách chia chunk. B–C chỉ đổi filter. Đây là fixed-character/paragraph **có giới hạn token chung**, không mô tả sai A là mọi chunk đều dài 500 ký tự. Phép chia tiếp giữ các span nguồn; không bảo đảm mọi fragment tự đủ nghĩa.

[Benchmark frozen](../../benchmark/freeze.json) được tạo trước retrieval lúc `2026-11-14T03:35:36.822942+00:00`: **20 câu tiếng Anh**, q01–q15 dev thuộc chương 2/3/5/7, q16–q20 test thuộc chương 10/11. Có 5 câu trực tiếp, 5 diễn đạt lại, 10 điều kiện; q03/q07 dev và q17/q18 test có chapter nêu rõ trong câu. Có 24 evidence spans tính cả bốn alternative passages. Mọi quote/offset được kiểm tra trong normalized text và trích lại từ 22 trang PDF nguồn. Giữ nguyên benchmark và snapshot sau khi chạy.

Metric chính: một chunk đúng source/page và chứa **toàn bộ** một gold quote chính/thay thế sau NFC + whitespace folding. Hit@1 xét rank 1; Evidence Hit@3 xét ít nhất một trong ba chunk. Không cộng các fragment để biến thành single-chunk hit; không tăng hit chỉ vì đúng trang. Không thêm equivalence override sau khi xem kết quả: các đoạn có thể tương đương về ý nghĩa vẫn cần người chấm xác nhận nếu muốn dùng để điều chỉnh metric. Grounding semantic được báo riêng để thấy giới hạn của literal matching.

Tiêu chí chọn có trước test, theo [protocol](../../benchmark/protocol.json): ưu tiên dev Hit@3, rồi dev Hit@1, ingest time thấp hơn, số chunk ít hơn, cuối cùng tên chiến lược theo alphabet. C được tính chi phí ingest của B khi tie-break, không coi việc tái sử dụng là ingest bằng 0. B và C hòa ở mọi tiêu chí số; **B thắng tie-break alphabet**, được khóa lúc `2026-11-14T05:00:53.613036+00:00`. Test bắt đầu sau đó lúc `2026-11-14T05:00:53.625824+00:00`. [Dev selection](../../results/dev_selection.json) giữ SHA-256 code/config/chunks/dev outputs; [validation](../../results/run_validation.json) xác nhận lock không đổi.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count |
|---|---|---|---|---:|
| A | dev | 3/15 (20,0%) | 7/15 (46,7%) | 244 |
| B | dev | 7/15 (46,7%) | 11/15 (73,3%) | 229 |
| C | dev | 7/15 (46,7%) | 11/15 (73,3%) | 229, dùng B |
| A | test | 2/5 (40,0%) | 2/5 (40,0%) | 244 |
| B | test | 2/5 (40,0%) | 3/5 (60,0%) | 229 |
| C | test | 2/5 (40,0%) | 3/5 (60,0%) | 229, dùng B |

Không câu nào thiếu top-3; lỗi backend không được biến thành response rỗng để chấm. Trace đủ question/gold/filter/IDs/text/score/metadata/timing/nhãn hit tại [dev](../../results/retrieval_dev.jsonl), [test](../../results/retrieval_test.jsonl); tử/mẫu và rate trong [retrieval_metrics.json](../../results/retrieval_metrics.json).

| Strategy | Tổng ký tự kể overlap | Token kể special tokens | Độ dài chunk min/median/max (ký tự) | Chunking (s) | Embedding (s) | Ghi DB lần đầu (s) | Ingest embedding + DB (s) |
|---|---:|---:|---|---:|---:|---:|---:|
| A | 84.107 | 21.584 | 1 / 465 / 500 | 0,895 | 11,456 | 0,125 | 11,581 |
| B | 76.707 | 19.568 | 5 / 385 / 500 | 0,345 | 12,000 | 0,097 | 12,098 |
| C | Dùng B | Dùng B | Dùng B | Dùng B | Không encode riêng | Không ghi riêng | Dùng B: 12,098 |

Model load ingest mất 6,540 s, ghi riêng ngoài ingest embedding+DB. Tổng document inputs 473; token dài nhất 128. Các histogram 100 ký tự/bucket ở [chunking_stats.json](../../results/chunking_stats.json). **Paid API = 0 USD** cho mọi cấu hình; không tính điện, phần cứng, dung lượng tải model. A có 15 vector nhiều hơn B nhưng nhanh hơn 0,516 s ở lần chạy này; không suy luận tốc độ tổng quát từ một lượt CPU.

Dev query embedding tổng 0,439 s cho 15 câu; test 0,146 s cho 5 câu, encode **một lần mỗi câu**, chia sẻ A/B/C. Tổng search dev A/B/C lần lượt 0,043/0,036/0,034 s; test 0,023/0,018/0,014 s. Chạy tuần tự, không load test, không hiệu chỉnh cache/warm-up; số thời gian không phải SLA hay benchmark throughput.

### Coherence, metadata và grounding

**Các nhãn định tính là AI-reviewed và đang chờ học viên xác nhận.** Codex đọc các chunk/trace, ghi score và lý do cụ thể; script chỉ kiểm tra nguồn, đủ mẫu và cộng điểm. Không có dịch vụ LLM judge riêng. Reviewer biết nội dung/gold và kết quả retrieval nên có nguy cơ thiên lệch; không phải chấm mù/độc lập.

| Strategy | Coherence /2 (n=10) | Metadata đủ và đúng trên test | Top-3 đúng phạm vi filter dev | Top-3 đúng phạm vi filter test | Grounding 0/1/2 (số câu, n=5) | Grounding /2 |
|---|---:|---|---|---|---|---:|
| A | 1,0 | 15/15 | 1/2 | 1/2 | 2 / 0 / 3 | 1,2 |
| B | 1,8 | 15/15 | 1/2 | 0/2 | 2 / 0 / 3 | 1,2 |
| C | 1,8 | 15/15 | 2/2 | 2/2 | 2 / 0 / 3 | 1,2 |

**Coherence:** dùng đúng 10 vị trí đã frozen trên các trang 31–36, 39–42. Chọn chunk chứa anchor gần midpoint nhất, tie theo start rồi ID; cùng vị trí cho A/B/C. Đọc toàn chunk, chấm 0 không hiểu được vì mất chủ thể/ý; 1 hiểu một phần nhưng thiếu ngữ cảnh; 2 tự đủ ý. A có 10 nhãn 1 do các phần cuối bị cắt hoặc tham chiếu thiếu; B có hai nhãn 1 (c02 ví dụ SyntaxError bị tách, c03 tham chiếu code trang trước) và tám nhãn 2. C cùng chunk B nên không phải 10 quan sát độc lập thêm. Lý do từng mẫu và chunk chính xác có trong [audit_labels.json](../../results/audit_labels.json), ngữ cảnh tại [audit_packets.json](../../results/audit_packets.json).

**Metadata:** kiểm tra đủ 5 test × top-3 × 3 chiến lược = **45 bản ghi**; tất cả có ID/URL/trang/chapter đúng manifest và source span. Re-extract lại các trang 111/112/113/114/125/126/128, đối chiếu text, header và trang in. Không phát hiện lỗi metadata trong mẫu; 45 bản ghi có trùng chunk giữa câu/chiến lược nên không đại diện cho 45 đơn vị độc lập. Metadata đúng không đồng nghĩa retrieval hữu ích: B-q17 rank 3 ở trang 128 chapter 11 là metadata đúng nhưng sai phạm vi chapter 10 người dùng yêu cầu; B-q18 rank 3 là trang 112 chapter 10, không đúng chapter 11. C loại cả hai, đạt filter 2/2 test. A/B chủ đích không lọc nên số này đo mức phù hợp yêu cầu input, không phải lỗi triển khai filter của A/B.

**Grounding:** đọc cả ba chunk của q16–q20 cho từng cấu hình, chấm 0 không có bằng chứng trả lời; 1 có nhưng thiếu điều kiện/ngữ cảnh; 2 đủ trả lời và truy nguồn. Các q16/q17/q18 được chấm 2; q19/q20 được chấm 0 ở cả A/B/C. A-q18 có đủ nội dung key/value trong top-3 để hiểu, nhưng gold quote bị cắt nên strict single-chunk Hit@3 vẫn là 0. Không sửa metric dựa vào nhãn grounding. Đây là **độ đủ của evidence retrieval**, không phải độ chính xác câu trả lời chatbot/LLM; không có chatbot được đánh giá.

## Phân tích và kết luận

**A–B:** B tăng dev Hit@1 và Hit@3 thêm 4/15, test Hit@3 thêm 1/5, đồng thời giảm từ 244 xuống 229 vector và giảm token lặp. B giữ đoạn tốt hơn trên mẫu coherence. Tuy nhiên, giới hạn 128 token và ranh giới trang vẫn làm đứt ngữ cảnh; không bảo đảm mọi paragraph là một ý hoàn chỉnh. A có fragment chỉ một ký tự, B ngắn nhất năm ký tự: đây là hạn chế thật của chia tiếp một span để vừa token budget; đã ghi nhận, không sửa dựa vào test.

**B–C:** filter cải thiện tuân thủ phạm vi test từ 0/2 lên 2/2, không tăng Hit@1/Hit@3 trong bộ này, không cải thiện grounding của các câu thiếu evidence. Với 16 câu không có filter, B/C trả **đúng cùng IDs/text/score/metadata**. Filter chỉ hữu ích khi input cung cấp chapter đúng và metadata đáng tin; có thể loại mất bằng chứng nếu người dùng chọn sai chapter. Không suy ra bộ lọc luôn tăng độ chính xác.

Các ví dụ lỗi có thể kiểm chứng trực tiếp từ trace:

| ID / cấu hình | Gold / kết quả thực tế | Phân tích |
|---|---|---|
| q18 / A | Gold trang 126; top-3 đều ở trang 126 nhưng không chunk nào chứa trọn quote | Trả đúng trang chưa đủ single-chunk hit; A cắt đầu đoạn membership. B/C giữ full quote tại rank 2. Grounding top-3 của A vẫn được chấm 2, minh họa khác biệt hai phép đo. |
| q19 / A/B/C | Gold trang 127 về `get(key, default)`; top-3 chủ yếu trang 125–126 | Dense retrieval nhầm sang membership/ngoặc vuông. Đoạn KeyError không trả lời hành vi get/default; grounding 0. C không có input filter nên giữ nguyên B. |
| q20 / A/B/C | Gold trang 128 về reverse lookup; top-3 trang 125–126 | Lấy nội dung key/value chung, thiếu cả khả năng nhiều keys cùng value và việc phải search. Hit@3=0, grounding 0. |

**Chọn B** theo rule dev đã khóa. C là biến thể có ích khi yêu cầu giới hạn chapter là một phần hợp đồng truy vấn, dù ở đây không làm tăng hit. Không thay lựa chọn sau khi biết test. Test năm câu chỉ có hai chương, mỗi câu tương ứng 20 điểm phần trăm; chênh lệch 2/5 và 3/5 không chứng minh ưu thế tổng quát.

Giới hạn khác: chỉ một sách tiếng Anh; câu hỏi cùng một tác giả soạn và AI hỗ trợ; người soạn biết test từ lúc tạo nên holdout là không tune theo test, không phải mù nội dung. Mẫu coherence chỉ chương đầu. Nhãn semantic cần con người xác nhận; strict full-quote có thể bỏ sót diễn đạt tương đương. Text không tái tạo đầy đủ hình/diagram; giữ hyphenation và phiên bản Python lịch sử, không diễn giải sách thành mô tả mọi hành vi Python hiện tại. Các bảng thời gian chỉ một máy/một lượt, có ảnh hưởng warm cache và thứ tự A/B/C.

Nếu mở rộng, dùng dev mới để thử chunk theo token có ranh giới câu, ghép ngữ cảnh xuyên trang hoặc cải thiện fragment nhỏ; thêm nhiều sách/chủ đề và holdout mới; có người chấm độc lập; cân nhắc hybrid cho q19/q20. Đây là đề xuất chưa chạy, không ghi thành cải tiến đã được chứng minh.

## Tái lập và các file nộp

Lệnh setup/chạy đầy đủ và lịch sử thay đổi: [starter/CHANGELOG.md](../../starter/CHANGELOG.md). README/đề bài gốc được giữ nguyên theo yêu cầu người dùng; hướng dẫn hiện hành trong changelog. Code nằm hoàn toàn trong `starter/`; dữ liệu/benchmark/results ở root đúng cấu trúc bài nộp.

Từ `starter/`, sau setup và ingest, benchmark theo thứ tự:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m src.run benchmark --split dev
HF_HUB_OFFLINE=1 .venv/bin/python -m src.run benchmark --split test
.venv/bin/python scripts/prepare_audits.py
# Đọc packet và ghi nhãn có reviewer/method trong results/audit_labels.json.
# Không tự sinh nhãn semantic từ metric hoặc coi AI label là human label.
.venv/bin/python scripts/summarize_results.py
RUN_PGVECTOR_TESTS=1 HF_HUB_OFFLINE=1 .venv/bin/python -m unittest discover -s tests
```

Pipeline từ chối ghi đè split outputs đã có và kiểm tra lock trước test. Để **kiểm tra bài nộp hiện có**, chỉ cần validator + summarize + tests, không rerun ingest để thay timing đã khóa. Để tái chạy retrieval, dùng checkout/thư mục riêng, giữ nguyên benchmark frozen; lưu bộ output cũ ra ngoài working copy rồi chạy ingest → dev → test. Không coi rerun trên cùng test là một test mới độc lập. Nhãn cần rà lại nếu artifacts thay đổi; không tái dùng nhãn có checksum khác.

Phiên bản chính: Python 3.12.16; pypdf 6.21.4; Poppler 26.01.0; torch 2.15.0+cpu; sentence-transformers 6.3.0; transformers 5.23.0; psycopg 3.3.8. Danh sách môi trường thực tế ở [environment.txt](../../results/environment.txt), dependency tối thiểu trong [requirements-embedding.txt](../../starter/requirements-embedding.txt). Không seed ngẫu nhiên: split và sampling có quy tắc cố định, model ở eval mode, exact search tie theo chunk ID; sai số float nhỏ vẫn có thể phụ thuộc môi trường.

[Experiment log](../../artifacts/experiment_log.csv) ghi cấu hình, giả thuyết thiết kế và kết quả; CSV được tổng hợp sau chạy, không giả nhận là log giả thuyết preregistered riêng. [Audit summary](../../results/audit_summary.json) giữ cả provenance reviewer và trạng thái chưa xác nhận human. Kết quả Gemma/Qdrant cũ nằm riêng trong `results/archive/embeddinggemma2_qdrant/`, không dùng trong bảng hiện hành.

Kiểm tra local cuối: **53 tests đạt**, có bốn kiểm thử PostgreSQL thật; snapshot/selection lock đúng; đủ 60 trace/180 hits và 30/15/45 mẫu audit; `pip check` không phát hiện dependency lỗi. Không commit `.env`, weights hoặc virtualenv.

**Phát hành:** đã push nhánh `feat/data-ingestion` tại commit `58af8c6fd328ef28896e008b09df30cecb90a36d`, merge bằng Git `--no-ff` và push `main` tại [commit chốt triển khai `7801c7f`](https://github.com/laitrongduc/K5-L3B-DAY06-LaiTrongDuc-2A202604019-DataIngestion/commit/7801c7f5330174cc1a5718665478aa19249dda12). GitHub xác nhận merge base đúng commit triển khai và không có khác biệt file ở bước merge. GitHub connector không tạo được PR do HTTP 403, nên dùng Git trực tiếp theo yêu cầu người dùng. Các cập nhật sau merge chỉ ghi metadata phát hành/checksum tài liệu, không thay code, cấu hình, gold, trace hoặc số đo benchmark; STUDENT.md ghi SHA merge này để tránh tham chiếu SHA tự chứa chính nó.
