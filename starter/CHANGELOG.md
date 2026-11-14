# Nhật ký thay đổi — Data Ingestion

Nhật ký phục vụ giải thích mã nguồn, tái lập thí nghiệm và viết báo cáo cá nhân.

## Cách làm hiện tại — sau khi đơn giản hóa

Phần này là hướng dẫn hiện hành. Các mục phía dưới giữ lịch sử thực hiện, gồm cả chức năng/tệp đã bổ sung rồi bỏ; không cần làm lại các bước lịch sử.

- **Code:** `starter/src/`, script trong `starter/scripts/`, tests trong `starter/tests/`.
- **Dữ liệu:** `data/`; **benchmark:** `benchmark/`; **kết quả:** `results/` ở root repo.
- Đã có 40 trang corpus, 20 câu (15 dev/5 test), evidence, 10 vị trí coherence cố định. Cấu hình hiện hành dùng **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` + PostgreSQL/pgvector**, 384 chiều, cosine. Đã nạp thật A=244, B=229; C dùng chung chunks/vector của B và lọc theo input câu hỏi. **Đã chạy benchmark dev/test**: 60 trace/180 hits; chọn B trên dev rồi mới chạy test. Có 30/15/45 mẫu coherence/grounding/metadata đã được Codex đọc/đánh giá và ghi rõ AI reviewer; **chưa có xác nhận nhãn thủ công của học viên**.
- Bộ chấm chỉ giữ **Hit@1, Evidence Hit@3, n/N theo dev/test**, trace top-3 và tuân thủ filter. Chỉ tính hit khi đúng nguồn/trang và đủ evidence chính/thay thế.
- Metadata đúng/đủ, coherence và grounding được đánh giá từ chunk/trace và nguồn theo GUIDE, có lý do từng mẫu. Không có equivalence override; metric chính giữ full-quote single-chunk. Nhãn định tính do AI đánh giá được tách rõ khỏi kiểm tra tự động và nhãn human. Không cần hệ thống pool review riêng.
- Giữ cùng corpus/model/store/câu hỏi cho A/B/C; chỉ chỉnh cấu hình trên dev. Giữ các giới hạn đã biết: test 5 câu, một nguồn, mẫu coherence ở các chương đầu.
- Các nguồn tham khảo vẫn nằm trong mục lịch sử “Tham khảo nguồn uy tín”; đã bỏ registry JSON và script báo cáo chất lượng riêng vì trùng thông tin.

Kiểm tra kết quả đã có từ **root repo**, sau khi đã có môi trường Python và Poppler:

```bash
starter/.venv/bin/python starter/scripts/validate_benchmark.py
starter/.venv/bin/python starter/scripts/summarize_results.py
RUN_PGVECTOR_TESTS=1 HF_HUB_OFFLINE=1 starter/.venv/bin/python -m unittest discover -s starter/tests
```

Không tạo lại freeze để chấp nhận dữ liệu đổi. Cấu hình chunk nằm ở `starter/strategies.json`; đầu ra ở `results/chunks_A.jsonl`, `results/chunks_B.jsonl` và `results/chunking_stats.json`. Cả A/B được chia tiếp nếu vượt 128 token, giữ nguyên đoạn văn bản và offsets; không truncate âm thầm. Đã đánh giá test sau khi khóa lựa chọn dev; **không chỉnh cấu hình theo test**. Tài liệu đề bài được giữ nguyên; ghi chú tiến độ chỉ ghi vào changelog.

Dependency bổ sung: `starter/.venv/bin/python -m pip install -r starter/requirements-embedding.txt`. Model được pin revision trong `starter/model_config.json`, cache ở `starter/.venv/model_cache`; lần đầu cần tải model qua Hugging Face với đúng revision/cache này, sau đó chạy offline. PostgreSQL khởi động bằng `docker compose -p day6_student_starter -f starter/docker-compose.yml up -d --wait` từ root (máy hiện tại cần người dùng chạy với sudo). Đặt `DATABASE_URL` trong `starter/.env` theo hướng dẫn setup của starter; không đưa secret vào Git.

Chạy pipeline từ **`starter/`**, sau khi PostgreSQL đã sẵn sàng:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m src.run ingest
HF_HUB_OFFLINE=1 .venv/bin/python -m src.run search --question "In Chapter 2, what is a Python variable?" --chapter 2
HF_HUB_OFFLINE=1 .venv/bin/python -m src.run benchmark --split dev
HF_HUB_OFFLINE=1 .venv/bin/python -m src.run benchmark --split test
.venv/bin/python scripts/prepare_audits.py
# Đọc packet, ghi nhãn có reviewer/method vào results/audit_labels.json.
.venv/bin/python scripts/summarize_results.py
RUN_PGVECTOR_TESTS=1 HF_HUB_OFFLINE=1 .venv/bin/python -m unittest discover -s tests
```

Biến `RUN_PGVECTOR_TESTS=1` bật bốn kiểm thử tích hợp database; bỏ biến này sẽ skip chúng. Trong môi trường sandbox hiện tại, kết nối database local cần quyền chạy ngoài sandbox. Kết quả hiện hành ở `results/vector_ingestion_stats.json`, `results/vector_smoke.json`; lịch sử Gemma2/Qdrant được lưu riêng ở `results/archive/embeddinggemma2_qdrant/`.

Các lệnh ingest → benchmark ở trên dùng cho **một lần chạy mới trong checkout riêng**; split outputs đã có sẽ bị từ chối ghi đè. Không rerun ingest ở working copy kết quả đã khóa để thay timing/cấu hình. Giữ bộ output cũ bên ngoài working copy trước khi tái chạy; không thay benchmark frozen, và không coi lần chạy lại cùng test là holdout mới. Để kiểm tra bài hiện tại, dùng ba lệnh validator/summarize/tests ở trên.

Setup lần đầu (từ `starter/`, cần Python 3.11–3.14, Poppler và Docker; môi trường thực tế đã kiểm tra dùng Python 3.12.16):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-embedding.txt
# Chỉ tạo .env nếu chưa có; giữ cấu hình cá nhân nếu đã tồn tại.
cp -n .env.example .env
.venv/bin/hf download sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  --revision e8f8c211226b894fcb81acc59f3b34ba3efd5f42 \
  --cache-dir .venv/model_cache \
  --include "*.json" --include "model.safetensors" --include "sentencepiece.bpe.model"
docker compose -p day6_student_starter up -d --wait
.venv/bin/python scripts/check_setup.py
```

PDF đã nằm trong `data/raw/`; nếu thiếu, từ root tải bằng `curl -fL https://greenteapress.com/thinkpython2/thinkpython2.pdf -o data/raw/thinkpython2.pdf`, rồi so checksum manifest. Để tái tạo corpus/chunks trước lần ingest mới, từ root chạy `starter/.venv/bin/python starter/scripts/prepare_corpus.py`, validator, rồi `HF_HUB_OFFLINE=1 starter/.venv/bin/python starter/scripts/prepare_chunks.py`. Nếu checksum không khớp, dừng để xem khác biệt; không cập nhật freeze cho qua lỗi.

Báo cáo hiện hành: `report/individual/2A202604019_LaiTrongDuc.md`; cấu hình/giả thuyết thiết kế và số đo: `artifacts/experiment_log.csv`; metric tổng hợp: `results/retrieval_metrics.json`; nhãn/provenance: `results/audit_labels.json`; kiểm tra chéo: `results/run_validation.json`.

## Quy ước làm việc

- Nhánh triển khai: `feat/data-ingestion`.
- Viết mã nguồn, script và kiểm thử phục vụ triển khai trong `starter/`; mã pipeline đặt tại `starter/src/`.
- Dữ liệu và cấu hình chọn corpus đặt trong `data/` ở root; kết quả đặt trong `results/`, benchmark đặt trong `benchmark/`, theo cấu trúc `SUBMISSION.md`. Các đường dẫn dữ liệu/kết quả trong hướng dẫn hiện hành bên dưới tính từ root repo.
- Cập nhật nhật ký sau mỗi nhóm thay đổi có ý nghĩa, ghi rõ file/hàm, nội dung thay đổi, lý do, cách kiểm tra và kết quả thực tế.
- Phân biệt việc đã hoàn thành, chưa kiểm tra và còn tồn tại. Không ghi kế hoạch hoặc kết quả giả định thành việc đã làm.
- Khi chạy thí nghiệm, ghi cấu hình A/B/C, model, phiên bản dữ liệu/benchmark, lệnh chạy và đường dẫn artifacts. Giữ số liệu chi tiết trong experiment log và kết quả thực nghiệm; dẫn đường tới các file đó từ nhật ký.
- Không tự ý thêm ghi chú tiến độ, giải thích hoặc báo cáo vào các tệp có sẵn. Tập trung các nội dung này tại `starter/CHANGELOG.md`. Chỉ sửa mã nguồn/cấu hình hiện có khi cần trực tiếp cho nhiệm vụ triển khai.
- Không ghi secret, API key hoặc thông tin kết nối nhạy cảm.

## 2026-11-14 — Khởi tạo nhánh và nhật ký

### Đã thực hiện

- Đọc các tài liệu yêu cầu: `README.md`, `GUIDE.md`, `RULES.md`, `RUBRIC.md`, `CHECKPOINTS.md`, `BENCHMARK.md`, `SUBMISSION.md`, thông tin học viên và mẫu báo cáo.
- Đọc tài liệu setup và toàn bộ các module Python của starter. Xác nhận pipeline còn là khung TODO, chưa có corpus thật, benchmark hoàn chỉnh hoặc kết quả thực nghiệm.
- Lập kế hoạch trong cuộc trao đổi: chuẩn bị corpus tối thiểu 30 trang nội dung, cố định benchmark tối thiểu 15 dev/5 test, triển khai A/B/C, đánh giá năm khía cạnh và hoàn thiện bài nộp.
- Tạo và chuyển từ `main` sang nhánh `feat/data-ingestion` để triển khai bài làm.
- Thống nhất phạm vi code trong `starter/` theo yêu cầu của người dùng.
- Tạo `starter/CHANGELOG.md` để lưu lịch sử thay đổi phục vụ giải thích và báo cáo.

### Lý do

- Làm việc trên nhánh riêng để các thay đổi có thể được xem xét trước khi tích hợp.
- Tập trung mã triển khai trong starter hiện có và duy trì bằng chứng về quá trình thực hiện.

### Kiểm tra và trạng thái

- Lệnh `git switch -c feat/data-ingestion` đã thành công sau khi được cấp quyền ghi vào `.git`.
- Trước khi thay đổi, working tree có thư mục `.vscode/` chưa được Git theo dõi; không chỉnh sửa thư mục này.
- Chưa sửa logic pipeline, cài dependency, khởi động database, tải model hoặc chạy benchmark. Chưa có số liệu để báo cáo.

## 2026-11-14 — Chuẩn bị corpus Python cơ bản và triển khai ingestion

### Đã thực hiện

- Chọn **Think Python, 2nd Edition, Version 2.4.1** của Allen B. Downey; kiểm tra quyền CC BY-NC 3.0 trên trang tác giả và trang bản quyền PDF vật lý 4.
- Tải bản gốc vào `data/raw/thinkpython2.pdf`, giữ nguyên PDF và ghi nguồn, tác giả, ngày truy cập cùng SHA-256 trong `data/corpus_config.json`.
- Chọn 40 trang vật lý thuộc chương 2, 3, 5, 7, 10, 11; không tính front matter, trang trống và trang ngoài phạm vi. Dữ liệu là tiếng Anh.
- Hoàn thiện `src/ingestion.py`: đọc PDF, chuẩn hóa NFC và xuống dòng, giữ thụt dòng/đoạn/phép toán, ghi log lỗi/trang rỗng và loại running header có đối chiếu số trang/chương.
- Thử pypdf default/layout trên mẫu, phát hiện từ dính quanh inline font. Chọn Poppler `pdftotext -layout` để trích text chính thức; dùng pypdf kiểm tra cấu trúc/số trang. Không fallback âm thầm.
- Thêm `scripts/prepare_corpus.py`: xác minh checksum, kiểm tra khoảng trang/heading chương, tạo metadata truy vết, kiểm tra đủ 30 trang và xuất manifest/text/thống kê/log.
- Xuất `data/manifest.json`, `data/processed/pages.jsonl`, `results/ingestion_stats.json` và `results/ingestion_errors.jsonl`.
- Thêm 9 kiểm tra tại `tests/test_ingestion.py`.
- Viết `data/README.md` với attribution, phạm vi, quy tắc đếm, lệnh tái tạo và giới hạn; cập nhật `README.md` và chú thích dependency hệ thống trong `requirements.txt`.
- Đối chiếu 6 trang render với text; ghi kết quả tại `results/corpus_quality_review.md`. Các kiểm tra hình ảnh do AI hỗ trợ, chưa phải audit thủ công benchmark của học viên.

### Lý do

- Corpus cơ bản dễ kiểm chứng đáp án, có các chương rõ ràng để dùng `chapter` làm filter theo yêu cầu câu hỏi/ngữ cảnh.
- Giữ số trang PDF vật lý và số in trong sách riêng để tránh trích sai nguồn khi tạo gold evidence.
- Checksum và cấu hình trang cố định bảo vệ tính nhất quán của corpus khi URL gốc cập nhật.
- Không ghép từ ngắt dòng hoặc sửa code nhằm tránh thay đổi nghĩa; ghi giới hạn để thiết kế benchmark phù hợp.

### Kiểm tra và kết quả

- Tạo môi trường `starter/.venv`; cài phần dependency cần thiết cho ingestion: pypdf 6.21.4. Môi trường Python 3.12.16, Poppler 26.01.0. Chưa cài toàn bộ dependency database/embedding.
- Lệnh tải ban đầu bị sandbox chặn DNS; tải thành công sau khi người dùng cấp quyền mạng. Không thay nguồn tải.
- Chạy `.venv/bin/python scripts/prepare_corpus.py` từ `starter/`: thành công; PDF có **244 trang**, chọn **40 trang**, tổng **76.707 ký tự**; không có trang rỗng trong corpus.
- Log có **1 trang rỗng: trang PDF 2**, không được chọn; không dùng OCR.
- Chạy `.venv/bin/python -m unittest discover -s tests -v`: **9 tests đạt**.
- Chạy lại xử lý corpus: text, manifest và log có SHA-256 giống lần trước; lưu so sánh trong `results/corpus_reproducibility.json`. Thời điểm chạy trong stats thay đổi theo thiết kế.
- Đối chiếu trang 31, 42, 61, 87, 111, 125: text và code đọc được; ghi nhận giới hạn sơ đồ và dấu gạch nối ngắt dòng.

### Tồn tại và việc tiếp theo

- Chưa xây benchmark. Bước tiếp theo: viết tối thiểu 20 câu hỏi, xác minh evidence, chia 15 dev/5 test trước khi thử retrieval; ít nhất 3 câu filter, gồm ít nhất 1 câu test.
- Chưa chọn embedding model, triển khai chunking/vector store/evaluation hoặc chạy A/B/C. Không có số liệu retrieval hay chi phí embedding.
- Chưa commit hoặc push. Không chỉnh sửa `.vscode/` hiện có.

## 2026-11-14 — Rà soát và thu gọn ghi chú theo yêu cầu

### Đã sửa

- Kiểm tra toàn bộ diff của các tệp đã được Git theo dõi: chỉ có `starter/README.md`, `starter/requirements.txt` và `starter/src/ingestion.py` bị thay đổi.
- Hoàn nguyên `starter/README.md` và `starter/requirements.txt` về đúng nội dung HEAD; bỏ các ghi chú/trạng thái đã tự thêm.
- Giữ thay đổi trong `starter/src/ingestion.py` vì đây là mã hiện thực nhiệm vụ đọc và chuẩn hóa PDF đã được yêu cầu.
- Chuyển nội dung hướng dẫn corpus và kiểm tra chất lượng từ hai tệp mới `starter/data/README.md`, `starter/results/corpus_quality_review.md` vào changelog bên dưới; bỏ hai tệp ghi chú riêng này.
- Sửa thông báo thiếu dữ liệu trong script mới để dẫn tới `starter/CHANGELOG.md`.
- Giữ dữ liệu, manifest, cấu hình, log, thống kê và kiểm thử đã tạo vì đây là đầu ra triển khai; không thay đổi dữ liệu corpus.
- Các đường dẫn tới hai tệp ghi chú trong mục lịch sử trước đây mô tả trạng thái tại thời điểm đó; nội dung hiện tại đã chuyển vào changelog.

### Quy ước từ đây

- Mọi ghi chú tiến độ, lý do thay đổi, hướng dẫn phát sinh và giải thích kết quả ghi vào changelog.
- Không tự chỉnh README/tài liệu đề bài hoặc thêm chú thích vào tệp cấu hình có sẵn để báo cáo tiến độ.
- Chỉ sửa tệp mã nguồn/cấu hình khi nhiệm vụ triển khai thực sự cần; ghi rõ thay đổi trong changelog.

### Kiểm tra

- Đối chiếu byte của README và requirements với HEAD sau hoàn nguyên.
- Không sửa logic xử lý hoặc dữ liệu ở lần rà soát này; kết quả 9 tests trước đó vẫn là lần kiểm tra mã gần nhất, không ghi thành lần chạy mới.

### Hướng dẫn corpus đã chuyển vào changelog

### Corpus: Python cơ bản cho sinh viên mới bắt đầu

#### Nguồn và quyền sử dụng

- **Think Python: How to Think Like a Computer Scientist**, Allen B. Downey.
- 2nd Edition, Version 2.4.1; copyright 2015 Allen Downey.
- Trang tác giả: https://greenteapress.com/wp/think-python-2e/
- PDF: https://greenteapress.com/thinkpython2/thinkpython2.pdf
- Giấy phép: [CC BY-NC 3.0 Unported](https://creativecommons.org/licenses/by-nc/3.0/), được ghi tại trang PDF vật lý 4 và trang tác giả.
- Dùng trong lab giáo dục phi thương mại, ghi công tác giả và nguồn. Giữ nguyên PDF gốc và thông báo bản quyền. Văn bản dẫn xuất được chọn trang, chuẩn hóa và bỏ running header; không dịch hoặc viết lại nội dung.
- Corpus tiếng Anh. Ngôn ngữ câu hỏi sẽ được ghi rõ khi xây benchmark; hiện chưa có benchmark hay kết quả retrieval.

#### Phạm vi

| Chương trong sách | Trang PDF vật lý | Trang in trong sách | Số trang |
|---|---|---|---:|
| 2: Variables, expressions and statements | 31–36 | 9–14 | 6 |
| 3: Functions | 39–48 | 17–26 | 10 |
| 5: Conditionals and recursion | 61–68 | 39–46 | 8 |
| 7: Iteration | 85–90 | 63–68 | 6 |
| 10: Lists | 111–115 | 89–93 | 5 |
| 11: Dictionaries | 125–129 | 103–107 | 5 |
| **Tổng** | | | **40** |

Các trang được chọn chứa giải thích, ví dụ hoặc glossary phục vụ học Python. Không tính bìa, bản quyền, lời nói đầu, mục lục, trang trắng hoặc nội dung ngoài các khoảng trên. Không nhân bản trang. Sách gốc có 244 trang; trang 2 không có text và không nằm trong corpus. Quy tắc tối thiểu 1.500 ký tự cho đơn vị text không phân trang không áp dụng cho các trang PDF này.

`page` luôn là số trang PDF vật lý, bắt đầu từ 1. `printed_page` là số in trong sách, bằng `page - 22` trong các khoảng được chọn. Không dùng lẫn hai hệ số trang khi tạo gold evidence.

#### Lấy dữ liệu và tái tạo

Chạy từ **root repo**, cần Python và Poppler (`pdftotext`, `pdftoppm`; trên Ubuntu gói `poppler-utils`). Giai đoạn này chưa cần database hoặc embedding model. Hướng dẫn này đã cập nhật theo lần chuyển cấu trúc bên dưới.

```bash
python3 -m venv starter/.venv
starter/.venv/bin/python -m pip install 'pypdf==6.21.4'
mkdir -p data/raw
curl -fL https://greenteapress.com/thinkpython2/thinkpython2.pdf -o data/raw/thinkpython2.pdf
starter/.venv/bin/python starter/scripts/prepare_corpus.py
starter/.venv/bin/python -m unittest discover -s starter/tests -v
```

SHA-256 của snapshot đã kiểm tra:

```text
6033000bac3f9268ad75ee041bf8e5d9a3bc8a33bb156399cbd014918cb59f94
```

URL tác giả có thể đổi nội dung. Script từ chối snapshot khác checksum; khi đó cần xem lại phiên bản, số trang, quyền và cấu hình thay vì tự động chấp nhận. `corpus_config.json` cố định nguồn và phạm vi trang. Không đổi `accessed_at` khi chỉ chạy lại xử lý trên cùng bản tải; khi lấy snapshot mới phải cập nhật thông tin nguồn.

#### Đầu ra và kiểm chứng

- `data/manifest.json`: thông tin nguồn/quyền, quy tắc đếm, toàn bộ 244 trang và số ký tự, trường metadata và giới hạn.
- `data/processed/pages.jsonl`: 40 bản ghi trang, mỗi trang có ID, URL, text, chương, số trang in và checksum nguồn.
- `results/ingestion_stats.json`: thống kê thực tế, phiên bản công cụ, thời điểm chạy.
- `results/ingestion_errors.jsonl`: log trang rỗng/cảnh báo/lỗi; tạo lại cho mỗi lần xử lý.
- Đối chiếu mẫu PDF với text và giới hạn: xem phần kiểm tra chất lượng trong changelog này.

Metadata filter chính là `chapter` kiểu integer, xác minh qua heading chương trong PDF. Chỉ dùng khi câu hỏi/ngữ cảnh đã chỉ rõ chương; không suy ra filter từ gold evidence.

Giữ nguyên thụt dòng code, heading, dấu câu và phép toán. Không ghép từ bị ngắt bằng dấu gạch nối cuối dòng vì có thể làm sai code. Sơ đồ không giữ được quan hệ hình học trong text; benchmark nên dựa trên đoạn giải thích/ví dụ đọc được và được xác minh.

### Kiểm tra chất lượng corpus — 2026-11-14

#### Phạm vi và phương pháp

- Người kiểm tra: Codex (AI hỗ trợ), đối chiếu hình render PDF và text đã chuẩn hóa. Đây chưa phải nhãn thủ công benchmark do học viên xác nhận.
- Nguồn: Think Python, 2nd Edition, Version 2.4.1; snapshot SHA-256 ghi trong `data/manifest.json`.
- Render bằng `pdftoppm` và đọc text từ `data/processed/pages.jsonl`.
- Mẫu: 6 trang PDF vật lý 31, 42, 61, 87, 111, 125; phủ cả 6 chương và có trang chứa code lồng nhau, phép toán, glossary/khái niệm và sơ đồ.
- Hình render phục vụ kiểm tra nằm trong `/tmp/python-corpus-review/`, không phải artifacts bắt buộc. Có thể tái tạo bằng lệnh bên dưới.

```bash
# Chạy từ root repo; thay 87 bằng số trang cần xem.
pdftoppm -f 87 -l 87 -scale-to 1200 -singlefile -png data/raw/thinkpython2.pdf /tmp/thinkpython-page-87
```

#### Kết quả đối chiếu mẫu

| Trang PDF | Trang in | Chương | Quan sát |
|---:|---:|---:|---|
| 31 | 9 | 2 | Heading, phần giải thích biến và ví dụ gán giá trị đọc được; ký hiệu π được giữ. Sơ đồ biến còn text nhưng mất mũi tên/quan hệ hình học. |
| 42 | 20 | 3 | Running header đã bỏ; định nghĩa hàm, câu lệnh thụt dòng và heading 3.5 còn nguyên. |
| 61 | 39 | 5 | Phân biệt phép chia `/`, `//` và `%`; số liệu ví dụ còn nguyên. |
| 87 | 65 | 7 | Running header đã bỏ; vòng lặp và nhánh if/else lồng nhau giữ thụt dòng; điều kiện kết thúc vòng lặp đọc được. |
| 111 | 89 | 10 | Heading, list rỗng, list lồng nhau và ví dụ nhiều kiểu phần tử đọc được. |
| 125 | 103 | 11 | Heading, mô tả dictionary, key/value và code thêm phần tử đọc được; từ ngắt cuối dòng vẫn giữ dấu gạch nối. |

#### Thống kê thực tế

- PDF gốc: 244 trang vật lý.
- Corpus được chọn: 40 trang, không trùng ID; 76.707 ký tự sau chuẩn hóa và loại running header.
- Trang ngắn nhất: 1.148 ký tự; dài nhất: 2.765 ký tự.
- Không có trang rỗng trong 40 trang được chọn.
- Log ghi một trang không có text: trang PDF 2, nằm ngoài corpus. Không áp dụng OCR.
- Metadata `chapter` có 6 giá trị: 2, 3, 5, 7, 10, 11; kiểm tra heading mở đầu từng khoảng trang bằng script.

#### Kiểm tra tự động và tái lập

- Lệnh: `.venv/bin/python -m unittest discover -s tests -v`, chạy từ `starter/`.
- Kết quả: **9 tests đạt**. Bao gồm chuẩn hóa Unicode, giữ đoạn/thụt dòng/phép toán, loại đúng running header, giữ trang rỗng và số trang, báo lỗi thiếu nguồn/công cụ, tính nhất quán metadata và code từ corpus thật.
- Chạy lại `scripts/prepare_corpus.py`: SHA-256 của `pages.jsonl`, `manifest.json` và `ingestion_errors.jsonl` không đổi. Bằng chứng: `corpus_reproducibility.json`.
- `run_at` trong `ingestion_stats.json` thay đổi theo mỗi lần chạy là chủ đích.
- Môi trường thực tế: Python 3.12.16, pypdf 6.21.4, Poppler 26.01.0.

#### Giới hạn và bước tiếp theo

- `pypdf` default/layout đã được thử trên mẫu và có từ bị ghép dính quanh inline font; chọn Poppler layout cho bản corpus chính thức. Không dùng kết quả pypdf làm text benchmark.
- Không tự ghép từ bị ngắt cuối dòng: tránh sửa nhầm code. Evidence sau này phải kiểm chứng trên chính text chuẩn hóa, không chỉ PDF.
- Không dùng quan hệ chỉ thể hiện bằng sơ đồ làm evidence nếu text chưa mô tả đủ.
- Các khoảng trang là trích đoạn; chưa bao phủ toàn bộ kiến thức/chương. Một số đoạn tiếp nối sang trang khác; khi viết benchmark cần chọn evidence đủ điều kiện và ngữ cảnh.
- Corpus tiếng Anh; chưa quyết định ngôn ngữ câu hỏi hoặc chọn model embedding.
- Chưa xây/chạy benchmark, chunking, embedding hoặc vector store. Kiểm tra chạy lại corpus không chứng minh tính idempotent của vector store.
- Học viên cần xem lại nguồn và mẫu đối chiếu để giải thích bài làm; không xem kiểm tra bằng AI là đánh giá độc lập của con người.

## 2026-11-14 — Sắp xếp đường dẫn theo cấu trúc bài nộp

### Đã thực hiện

- Đối chiếu `SUBMISSION.md`; giữ code trong `starter/`, chuyển dữ liệu và kết quả ra root repo.
- Di chuyển 7 tệp, kiểm tra SHA-256 ngay sau từng lần di chuyển, không ghi đè tệp đích có sẵn:

| Đường dẫn trước | Đường dẫn hiện tại |
|---|---|
| `starter/data/corpus_config.json` | `data/corpus_config.json` |
| `starter/data/manifest.json` | `data/manifest.json` |
| `starter/data/raw/thinkpython2.pdf` | `data/raw/thinkpython2.pdf` |
| `starter/data/processed/pages.jsonl` | `data/processed/pages.jsonl` |
| `starter/results/ingestion_errors.jsonl` | `results/ingestion_errors.jsonl` |
| `starter/results/ingestion_stats.json` | `results/ingestion_stats.json` |
| `starter/results/corpus_reproducibility.json` | `results/corpus_reproducibility.json` |

- Thêm `benchmark/.gitkeep` để Git giữ thư mục benchmark; chưa tạo câu hỏi hoặc gold giả.
- Cập nhật `starter/scripts/prepare_corpus.py`: xác định root repo từ vị trí script, đọc `data/` và ghi `results/` tại root, không phụ thuộc working directory.
- Cập nhật `starter/tests/test_ingestion.py`: đọc corpus tại root; cấu hình import để chạy được từ root và `starter/`.
- Cập nhật hướng dẫn hiện hành trong changelog theo đường dẫn mới. Các mục lịch sử trước đó giữ ý nghĩa là công việc tại thời điểm thực hiện.
- Không chỉnh README, requirements, tài liệu đề bài, experiment log mẫu, thông tin học viên hoặc mẫu báo cáo. Các tệp `.gitkeep` gốc trong `starter/data/` và `starter/results/` được giữ nguyên; không còn tệp dữ liệu/kết quả triển khai ở đó.

### Kiểm tra và kết quả

- Chạy script từ root repo, `starter/` và `/tmp`: cả 3 lần thành công, cùng 40 trang và 76.707 ký tự.
- PDF gốc, cấu hình corpus, manifest, text và log lỗi có checksum giống trước khi di chuyển. Chỉ thời điểm chạy trong stats thay đổi theo thiết kế.
- Cập nhật `results/corpus_reproducibility.json` bằng kết quả kiểm tra thực tế với đường dẫn mới và 3 working directory.
- Chạy `starter/.venv/bin/python -m unittest discover -s starter/tests -v` từ root: **9 tests đạt**.
- Chạy `.venv/bin/python -m unittest discover -s tests -v` từ `starter/`: **9 tests đạt**.

### Cấu trúc hiện tại và phần chưa hoàn thành

```text
STUDENT.md                         # mẫu gốc, chưa điền
README.md                          # tài liệu gốc, giữ nguyên
starter/
  src/                             # mã pipeline
  scripts/                         # setup và chuẩn bị corpus
  tests/                           # kiểm tra ingestion
  CHANGELOG.md                     # ghi chú và hướng dẫn hiện hành
data/
  corpus_config.json
  manifest.json
  raw/thinkpython2.pdf
  processed/pages.jsonl
benchmark/
  .gitkeep                         # chưa có câu hỏi
artifacts/
  experiment_log.csv               # mẫu gốc, chưa có thí nghiệm
results/
  ingestion_errors.jsonl
  ingestion_stats.json
  corpus_reproducibility.json
report/individual/
  MSSV_HoTen.md                     # mẫu gốc, chưa có báo cáo cá nhân
```

- Đường dẫn các thành phần đã bố trí theo đề. Benchmark, thí nghiệm và báo cáo cá nhân vẫn phải hoàn thành ở các bước tiếp theo; việc có thư mục không đồng nghĩa đạt yêu cầu nội dung bài nộp.
- Không commit hoặc push trong lần thay đổi này.

## 2026-11-14 — Xây và cố định benchmark trước retrieval

### Đã thực hiện

- Tạo `benchmark/questions.jsonl`: **20 câu hỏi tiếng Anh**, cùng ngôn ngữ corpus; mỗi câu có ID, split, loại câu, đáp án, nguồn, trang PDF vật lý, evidence nguyên văn và offset ký tự.
- Cố định **15 dev (q01–q15)** thuộc chương 2, 3, 5, 7 và **5 test (q16–q20)** thuộc chương 10, 11. Tách theo chương trước khi chạy retrieval, không dùng seed vì phân chia có chủ đích theo chủ đề.
- Phủ **5 câu trực tiếp, 5 câu diễn đạt lại, 10 câu điều kiện/ngoại lệ**. Không đưa câu không có đáp án trong nguồn vào chỉ số bắt buộc.
- Có **4 câu filter**: q03 (chương 2), q07 (chương 3) thuộc dev; q17 (chương 10), q18 (chương 11) thuộc test. Mỗi câu nêu rõ chương từ đầu, filter chỉ có `chapter`; không lấy gold source/page/answer để suy ra filter.
- Lưu **4 evidence thay thế** cho q01, q06, q07, q08; tổng cộng **24 đoạn evidence hợp lệ**. Giữ nguyên dấu câu, thụt dòng và ngắt dòng của text chuẩn hóa; offset tính từ 0, điểm cuối không bao gồm ký tự tại offset đó.
- Đọc từng cặp câu hỏi/đáp án/evidence, kiểm tra đủ các điều kiện cần trả lời. Khi rà soát q19, mở rộng evidence để bao gồm cả trường hợp key tồn tại và không tồn tại trước khi cố định benchmark.
- Render và đối chiếu toàn bộ **22 trang PDF** chứa evidence chính/thay thế với text. Đây là kiểm tra của Codex hỗ trợ tác giả, không ghi thành xác nhận độc lập của con người.
- Tạo `benchmark/protocol.json` làm cấu hình phương pháp: split, filter, metric, tiêu chí chọn chiến lược, cách chấm và các giới hạn.
- Tạo `benchmark/coherence_samples.jsonl` với **10 vị trí nguồn cố định**, chưa có nhãn/điểm.
- Thêm `starter/scripts/validate_benchmark.py`: kiểm tra schema, nguồn/trang, evidence/offset, split, filter, mẫu coherence; trích lại đúng trang PDF để đối chiếu; kiểm tra checksum snapshot.
- Thêm `starter/tests/test_benchmark.py`: 12 kiểm tra cho các lỗi có thể làm sai benchmark, gồm evidence sai, nhầm trang, thay split, câu trùng, filter không có trong query, filter dùng gold page hoặc loại mất gold, evidence thay thế không hợp lệ, sai vị trí coherence và thay đổi snapshot.
- Tạo `benchmark/freeze.json` sau khi kiểm tra đạt. Không sửa corpus, README, requirements, tài liệu đề bài hoặc các module pipeline hiện có trong bước này.

### Quy tắc thí nghiệm đã chốt

- A/B/C dùng cùng corpus, model, cách embedding, store, cosine, top-3 và bộ câu hỏi/gold. A–B chỉ đổi chunking; B–C giữ cùng chunk/vector, chỉ thay filter.
- Query embedding chỉ nhận trường `question`. Filter là input có sẵn từ câu hỏi. Đáp án, gold và lời giải thích chỉ dùng cho đánh giá, không đưa vào query/filter.
- Chọn cấu hình trên dev theo thứ tự: **Evidence Hit@3 cao hơn → Hit@1 cao hơn → ingest nhanh hơn → ít chunk hơn → thứ tự A/B/C nếu vẫn hòa**. Audit dùng giải thích chất lượng và đánh đổi; không dùng test để chỉnh cấu hình.
- Cố định cấu hình cuối trước khi chạy test. Báo riêng dev/test; giữ top-3 trace và tử số/mẫu số của Hit@1/Hit@3.
- Một hit bắt buộc có một chunk đúng nguồn/trang và đủ evidence; chấp nhận bất kỳ evidence chính/thay thế nào. Có thể chuẩn hóa NFC/khoảng trắng khi so khớp. Evidence tương đương mới phải có bản ghi audit, nguồn/trang, lý do và người xác nhận, áp dụng cùng tiêu chí cho mọi cấu hình; không tự sửa gold/test sau khi xem kết quả để làm đẹp số liệu.
- Evidence nằm rải qua nhiều chunk không tự tính thành hit của metric chính. Phân tích hợp bằng chứng đa chunk nếu có phải báo riêng.

### Cách chọn mẫu coherence

- Chọn 10 trang đầu sau khi sắp theo document ID và số trang PDF vật lý: **31, 32, 33, 34, 35, 36, 39, 40, 41, 42**.
- Trên mỗi trang, lấy đoạn đầu tiên có ít nhất 100 ký tự; lưu 160 ký tự đầu làm tham chiếu. Anchor nằm tại offset bắt đầu đoạn + min(80, độ dài đoạn − 1).
- Với mỗi chiến lược, chọn chunk chứa anchor và có trung điểm gần anchor nhất; hòa thì chọn start_char nhỏ hơn, rồi chunk_id. Nếu không có chunk bao phủ, ghi lỗi bao phủ và điểm 0; không bỏ mẫu.
- Chấm 0/1/2 theo GUIDE sau khi có chunk, cùng vị trí và quy tắc cho A/B/C. Hiện chưa có chunk hoặc điểm coherence. Mẫu này thiên về các chương đầu; đã công bố giới hạn.

### Kiểm tra và kết quả thực tế

- `starter/.venv/bin/python starter/scripts/validate_benchmark.py`: đạt trước khi freeze; khớp 20 câu, 15 dev/5 test, 4 câu filter, 24 evidence và 10 mẫu coherence.
- Đối chiếu evidence bằng offset chính xác trong text chuẩn hóa và trích lại PDF các trang **32, 33, 34, 35, 36, 39, 40, 44, 46, 48, 61, 64, 66, 68, 86, 87, 88, 113, 114, 126, 127, 128**: đạt.
- `starter/.venv/bin/python -m unittest discover -s starter/tests -v`: **21 tests đạt**, gồm 12 benchmark và 9 ingestion.
- `starter/.venv/bin/python starter/scripts/validate_benchmark.py --freeze`: thành công tại **2026-11-14T03:35:36.822942+00:00** (UTC), trước khi chạy retrieval.
- Chạy validator lại từ `starter/`: đạt, snapshot khớp. Kết quả kiểm tra máy lưu tại `results/benchmark_validation.json`.
- Thử gọi `--freeze` lần hai: từ chối với exit code 1, không ghi đè hoặc thay checksum snapshot.
- SHA-256 `benchmark/questions.jsonl`: `cb6e725d84b02d53285591f25e9bcd00c561d7c7f8ddb1bc612a3b3cc7f7b4f2`.
- SHA-256 `benchmark/freeze.json`: `8a3abce994762325377f725fd8be7128934a5184f53afd0e2fb123ffc92016f3`. File freeze chứa checksum của cả 3 tệp benchmark và 4 tệp corpus được ghim.
- Hình render tạm nằm ở `/tmp/python-benchmark-review/`; chỉ dùng đối chiếu, không phải kết quả benchmark retrieval.

### Cách kiểm tra lại (chạy từ root repo)

```bash
starter/.venv/bin/python starter/scripts/validate_benchmark.py
starter/.venv/bin/python -m unittest discover -s starter/tests -v
```

Không chạy lại `--freeze` để chấp nhận thay đổi; validator mặc định phải phát hiện thay đổi so với snapshot. Nếu thực sự cần benchmark mới, tạo phiên bản mới và ghi rõ lý do, thời điểm, việc đã xem test hay chưa; không ghi đè lịch sử để tiếp tục coi test cũ là độc lập.

### Giới hạn và việc tiếp theo

- Tác giả biết nội dung test khi xây bộ câu hỏi; holdout ở đây là không dùng kết quả test để tinh chỉnh, không phải người xây câu hỏi chưa từng nhìn thấy test.
- Một cuốn sách, 20 câu và chỉ 5 câu test thuộc hai chương; các khái niệm cơ bản vẫn giao nhau giữa các chương. Không suy rộng kết quả ra mọi dữ liệu Python.
- Kiểm chứng ngữ nghĩa có AI hỗ trợ; học viên cần đọc lại các cặp câu hỏi/đáp án/evidence để xác nhận và giải thích. Kiểm tra substring/PDF không tự chứng minh đáp án đúng ngữ nghĩa.
- Tránh câu hỏi về thứ tự dictionary hiện đại hoặc kiểu trả về của range vì bản sách chứa một số mô tả lịch sử không phù hợp Python hiện hành. Không thay nội dung nguồn để sửa lịch sử.
- **Chưa chạy retrieval, chưa tạo nhãn audit retrieval, chưa chọn model hoặc triển khai chunking.** Bước tiếp theo là hai cách chunk và ba cấu hình A/B/C, giữ nguyên benchmark đã ghim.
- Chưa commit hoặc push.

## 2026-11-14 — Tham khảo nguồn uy tín và tăng kiểm soát chất lượng benchmark

### Nguồn đã tham khảo và cách áp dụng

| Nguồn gốc | Nội dung tham khảo | Áp dụng vào bài |
|---|---|---|
| [Stanford IR, 8.1](https://nlp.stanford.edu/IR-book/html/htmledition/information-retrieval-system-evaluation-1.html) | Corpus, query và relevance judgments là các đầu vào riêng; dùng dev để tinh chỉnh | Giữ split và gold đã khóa; bắt buộc đủ trace cho từng câu/chiến lược |
| [Stanford IR, 8.5](https://nlp.stanford.edu/IR-book/html/htmledition/assessing-relevance-1.html) | Nhu cầu tìm kiếm thực tế và rà soát pool kết quả từ nhiều hệ thống | Chuẩn bị pool A/B/C, ẩn trường chiến lược/rank/score khi xem xét bằng chứng; nhãn chưa chấm giữ null |
| [BEIR, mã chính thức](https://github.com/beir-cellar/beir) và [bài NeurIPS 2021](https://datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/65b9eea6e1cc6bb9f0cd2a47751a186f-Abstract-round2.html) | Đầu vào đánh giá tách bạch và lưu kết quả truy xuất tái lập | Giữ trace đầy đủ, thêm MRR@3 dựa trên evidence như chỉ số bổ sung |
| [KILT, NAACL 2021](https://aclanthology.org/2021.naacl-main.200/) | Đánh giá provenance bên cạnh kết quả tác vụ | Tách kiểm tra nguồn/bằng chứng khỏi độ chính xác câu trả lời LLM |
| [NIST, Confidence intervals](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) | Công thức Wilson cho tỷ lệ theo mô hình nhị thức | Thêm khoảng 95% cùng n/N, công bố giả định và giới hạn mẫu nhỏ |

- Lưu URL, phạm vi áp dụng và ngày truy cập tại `benchmark/research_sources.json`. Hai mục Stanford được đọc qua nội dung lập chỉ mục của chính website; tải trực tiếp trang bị timeout, không dùng blog thay thế làm nguồn.
- Đây là cách áp dụng phương pháp phù hợp bài lab, không phải chạy nguyên benchmark BEIR/KILT hoặc được các nguồn này chứng nhận chất lượng.
- Quy định Hit@1/Evidence Hit@3 của đề giữ nguyên. Hit@3 không được đổi tên thành Recall@3. Không thêm nDCG khi chưa có bộ judgments phù hợp cho các chunk khác nhau giữa chiến lược.

### Thay đổi mã và artifacts

- Hiện thực `starter/src/evaluation.py` thay cho TODO:
  - `evaluate_query()`: giữ thứ tự top-3, yêu cầu đúng document ID/trang và đủ evidence, chấp nhận evidence thay thế; chỉ chuẩn hóa NFC/khoảng trắng khi khớp, không sửa phép toán hoặc tự ghép nhiều chunk để tính hit chính.
  - Giữ câu hỏi, text/ID chunk, score, metadata và evidence match trong trace. Không tự tạo điểm grounding/coherence hoặc kết luận metadata đúng chỉ vì đủ trường.
  - Phân biệt kết quả backend thành công nhưng rỗng với lỗi backend. Kết quả rỗng tính miss; trace lỗi hoặc thiếu trạng thái thành công làm dừng tổng hợp, không biến thành một lần truy xuất hợp lệ.
  - `summarize(..., questions=...)`: đối chiếu danh sách câu hỏi chuẩn, từ chối trace thiếu/trùng/sai split/chiến lược; tính lại từ hits thay vì tin cờ điểm do caller truyền vào.
  - Báo Hit@1 và Evidence Hit@3 có n/N, tách dev/test, loại câu và có/không filter. Khi không có câu filter, tỷ lệ filter là null (N/A); rỗng không tự tính tuân thủ filter.
  - Bổ sung strict evidence MRR@3, khoảng Wilson theo mô hình nhị thức và số câu thắng/thua/hòa khi so từng câu A–B, B–C. Đây là mô tả bổ sung, không thay tiêu chí chọn cấu hình đã khóa hoặc kiểm định ý nghĩa thống kê.
  - `prepare_review_pool()`: hợp nhất kết quả top-3 để rà soát; bản xem xét không chứa trường strategy/rank/score/chunk_id, bảng ánh xạ giữ riêng. Không tự gán không liên quan cho bằng chứng chưa được chấm.
- Thêm `starter/scripts/audit_benchmark_quality.py`: kiểm tra snapshot, thống kê độ phủ và ghi giới hạn tại `results/benchmark_quality_review.json`. Script này chỉ kiểm tra thiết kế; không nhận trace và không tạo số liệu retrieval.
- Thêm `starter/tests/test_evaluation.py`: **15 kiểm tra** cho định nghĩa metric, evidence thay thế, sai nguồn/trang, evidence bị chia, kết quả rỗng, lỗi backend, mẫu số, pool ẩn chiến lược và công thức khoảng Wilson.
- Mọi câu hỏi, đáp án, gold, protocol, mẫu coherence và dữ liệu trong snapshot gốc giữ nguyên. Phần tham khảo là mở rộng kiểm soát chất lượng; không tạo phiên bản câu hỏi mới vì không đổi tập/nhãn/metric chính.
- Không thêm ghi chú vào README, requirements hoặc tài liệu đề bài. Chỉ sửa module chấm điểm cần thiết cho yêu cầu benchmark; ghi phương pháp tại changelog này.

### Các giới hạn phát hiện qua kiểm tra thiết kế

- Dev: 15 câu, gồm 5 trực tiếp, 4 diễn đạt lại và 6 điều kiện; test: 5 câu, gồm 1 diễn đạt lại và 4 điều kiện, **không có câu nhãn trực tiếp**. Không báo hiệu quả trên nhóm test không có mẫu.
- Mỗi câu test thay đổi tỷ lệ 20 điểm phần trăm. Chỉ một cuốn sách, hai chương test; không suy rộng kết quả ra mọi tài liệu hoặc người dùng.
- Mẫu coherence cố định chỉ phủ chương 2 và 3. Giữ mẫu đã khóa và công bố phạm vi, không đổi mẫu sau khi xem chất lượng chunk.
- Gold thay thế chưa phải judgments vét cạn. Sau khi có retrieval, rà soát pool để ghi nhận evidence tương đương bị exact matching bỏ sót; mọi điều chỉnh chấm phải có lý do, người chấm và áp dụng nhất quán cho A/B/C.
- Pool theo chunk chỉ hỗ trợ rà soát. Grounding bắt buộc vẫn chấm **top-3 theo từng câu test**; coherence và metadata vẫn cần bảng nhãn riêng theo GUIDE.
- Giữ riêng điểm khớp tự động và kết quả audit có điều chỉnh. Không tự sửa file gold đã khóa hoặc áp dụng nhãn từ một cấu hình riêng lẻ cho riêng cấu hình đó.
- Chưa có đánh giá độc lập của con người. Các kiểm thử dùng ranked-hit fixtures có kiểm soát, không phải truy xuất thật hoặc embedding giả được dùng làm kết quả bài nộp.

### Kiểm tra thực tế

- `starter/.venv/bin/python -m unittest discover -s starter/tests -v`: **36 tests đạt** (9 ingestion, 12 kiểm tra benchmark, 15 bộ chấm).
- `starter/.venv/bin/python starter/scripts/validate_benchmark.py`: đạt; 20 câu, 15 dev/5 test, 24 evidence và checksum snapshot gốc không đổi.
- `starter/.venv/bin/python starter/scripts/audit_benchmark_quality.py`: chạy thành công; độ phủ và giới hạn lưu trong `results/benchmark_quality_review.json`.
- SHA-256 registry nguồn: `c03b1c8d47ba30aca236aed88af0ca63dec7baeb89040c9f52fb490861c6b100`; SHA-256 module chấm sau cập nhật: `7bc1134d79dd1ccdb385362090c1e82d28b148e86fb3d49531cb2b8f84575dca`. Report chất lượng ghi cả checksum freeze gốc và các đầu vào này.
- Chưa chạy embedding/vector search, chưa có pool từ trace thật, nhãn audit thủ công hay số liệu hiệu quả retrieval. Không coi bộ chấm đã có code là hoàn thành checkpoint 3:30.

### Lệnh kiểm tra lại và việc tiếp theo

```bash
starter/.venv/bin/python starter/scripts/validate_benchmark.py
starter/.venv/bin/python -m unittest discover -s starter/tests -v
starter/.venv/bin/python starter/scripts/audit_benchmark_quality.py
```

- Khi tích hợp runner, thêm trường strategy vào trace trả về từ `evaluate_query()`; truyền đúng danh sách câu dev hoặc toàn bộ benchmark vào `summarize()`. Chỉ gọi evaluator sau khi backend trả kết quả thành công.
- Trước khi viết số liệu cuối, thực hiện audit theo đề và rà soát evidence tương đương; không dùng test để tinh chỉnh.
- Bước triển khai tiếp theo vẫn là chunking để hoàn thành checkpoint 1:50. Chưa commit hoặc push.

## 2026-11-14 — Đơn giản hóa, giữ phần bắt buộc của bài

### Rà soát và quyết định

- Đối chiếu SUBMISSION, RUBRIC và GUIDE: cần corpus/manifest, benchmark dev/test có evidence, ba cấu hình có kiểm soát, embedding thật và vector store, trace top-3, Hit@1/Hit@3, audit năm khía cạnh và báo cáo tái lập.
- Chưa cần thêm chỉ số thống kê hoặc hạ tầng rà soát riêng để đáp ứng các yêu cầu trên. Tập trung vào chất lượng dữ liệu, truy vết và so sánh công bằng.

### Đã thay đổi

- Thu gọn `starter/src/evaluation.py` từ **199 xuống 108 dòng**, chỉ còn hai hàm công khai `evaluate_query()` và `summarize()` cùng helper chuẩn hóa chuỗi.
- Bỏ MRR, khoảng Wilson, bảng nhóm loại câu/filter, thống kê thắng/thua theo cặp và hệ thống pool review có bảng ánh xạ riêng. A–B/B–C vẫn được so sánh trên bảng kết quả và ví dụ lỗi theo đề.
- Giữ những kiểm tra có ảnh hưởng trực tiếp tới kết quả: nguồn/trang, đủ evidence, chấp nhận gold thay thế, không ghép nhiều chunk để tính hit chính, rank top-3, không mất câu khỏi mẫu số, trace không trùng, phân biệt lỗi backend với kết quả hợp lệ nhưng rỗng.
- Giữ thống kê tuân thủ filter; không có câu filter thì tỷ lệ là null (N/A). Không suy ra nhãn audit thủ công từ exact match.
- Bỏ `starter/scripts/audit_benchmark_quality.py`, `benchmark/research_sources.json` và `results/benchmark_quality_review.json`. Các nguồn, phát hiện về độ phủ và giới hạn đã được giữ trong lịch sử changelog nên không cần file/script trùng chức năng.
- Cập nhật `starter/tests/test_evaluation.py`: bỏ hai kiểm tra của các tính năng đã loại, giữ kiểm thử cho các trường hợp làm sai metric và mẫu số.
- Thêm phần “Cách làm hiện tại” ở đầu changelog với ba lệnh chính. Không xóa lịch sử; các hướng dẫn/tên tệp đã bỏ ở mục cũ được xem là lịch sử, không phải quy trình hiện hành.

### Phần giữ nguyên

- Corpus 40 trang, text chuẩn hóa, cấu hình nguồn và manifest.
- 20 câu, split 15 dev/5 test, 4 câu filter, 24 evidence, 10 vị trí coherence, protocol và freeze. Checksum các file snapshot không đổi; không tạo phiên bản benchmark mới.
- `starter/src/ingestion.py`, script chuẩn bị corpus và validator benchmark. Những phần này đang thực hiện các kiểm tra bắt buộc và đã chạy được nên không viết lại chỉ để giảm số dòng.
- Quy tắc chọn cấu hình trên dev, metric chính, phương pháp audit, cấu trúc thư mục và tài liệu đề bài. Không giảm yêu cầu nộp bài.

### Kiểm tra thực tế

- Chạy toàn bộ tests sau khi đơn giản hóa: **34 tests đạt** (9 ingestion, 12 benchmark, 13 evaluation). Số tests giảm từ 36 vì hai chức năng tùy chọn đã bỏ, không phải bỏ kiểm tra đang lỗi.
- Validator benchmark đạt, kiểm chứng lại evidence từ PDF và freeze gốc.
- So sánh bộ chấm cũ/mới bằng **120 trường hợp có kiểm soát** trên 20 câu: Hit@1, Hit@3, số kết quả và tuân thủ filter giống nhau.
- Tổng hợp cùng 60 trace kiểm thử (20 câu × A/B/C): cả **6 nhóm strategy/split** giữ nguyên n/N, tỷ lệ Hit@1/Hit@3 và filter compliance. Đây là regression fixtures, không lưu hoặc trình bày thành kết quả retrieval thật.
- Đối chiếu SHA-256 trước/sau: corpus, các tệp benchmark đã khóa, README/requirements gốc, ingestion và hai script chuẩn bị/kiểm chứng không đổi.
- Chưa chạy retrieval hoặc tạo nhãn audit. Chưa commit/push.

### Việc tiếp theo

- Hoàn thành chunking cố định cho A và theo đoạn cho B/C; giữ metadata truy nguồn, offset và ID ổn định.
- Sau đó mới triển khai embedding thật + vector store, thí nghiệm, audit và báo cáo theo các checkpoint còn lại.

## 2026-11-14 — Rà soát tính nhất quán và hoàn thành hai cách chunking

### Rà soát trước khi triển khai

- Kiểm tra code, cấu trúc thư mục, hướng dẫn hiện hành, benchmark và tests sau khi đơn giản hóa.
- Validator và toàn bộ **34 tests cũ đạt**; snapshot khớp; không có tham chiếu trong code đang chạy tới đường dẫn dữ liệu/kết quả cũ hoặc các chức năng đã bỏ.
- Giữ nguyên tài liệu đề bài; changelog là hướng dẫn hiện hành, các mục cũ là lịch sử. Không phát hiện mâu thuẫn đang chặn bước chunking.

### Đã triển khai

- Hoàn thiện `starter/src/chunking.py`:
  - `fixed_size()`: cửa sổ theo ký tự, overlap, không vượt ranh giới trang; dừng ngay khi đã đến cuối trang để tránh chunk đuôi dư.
  - `by_paragraph()`: gom các đoạn phân cách bởi dòng trống đến giới hạn; đoạn quá dài thì ưu tiên ngắt ở cuối dòng, sau đó khoảng trắng, cuối cùng cắt theo giới hạn cứng.
  - Giữ nguyên từng lát text, không strip/rewrite phần code; bỏ lát chỉ chứa whitespace. Giữ ID tài liệu, URL nguồn, số trang vật lý, metadata chương và thông tin phiên bản.
  - Bổ sung `start_char`/`end_char` (Unicode character, 0-based, end exclusive) để đối chiếu đúng text trang và chọn mẫu coherence.
  - `char_count` là độ dài **chunk**, `page_char_count` là độ dài trang; không để số ký tự trang bị hiểu nhầm thành độ dài chunk.
  - ID chunk được tạo xác định từ nguồn, phiên bản/hash trang, thuật toán/tham số và offset. Chạy lại cùng đầu vào cho cùng ID; dữ liệu/tham số đổi thì ID đổi.
- Thêm `starter/strategies.json` với tham số ban đầu đã nêu trong kế hoạch, không chọn theo kết quả test:
  - **A:** fixed-size 500 ký tự, overlap 50, không filter.
  - **B:** theo đoạn, tối đa 500 ký tự, không overlap, không filter.
  - **C:** trỏ tới chunks của B; khi truy xuất mới dùng filter có sẵn trong câu hỏi. Không tạo bộ chunk C khác B.
- Thêm `starter/scripts/prepare_chunks.py`: đọc corpus đã khóa, chia chunk, kiểm tra nguồn/offset/bao phủ/ID, xuất hai tệp JSONL và thống kê. Script không đọc câu hỏi để điều chỉnh hoặc chấm retrieval, chỉ xác minh checksum snapshot.
- Thêm `starter/tests/test_chunking.py` với 9 kiểm tra cho overlap, tham số lỗi, trang rỗng, đoạn dài/code, ID ổn định, metadata độc lập, source span, bao phủ corpus thật và 10 vị trí coherence đã cố định.

### Kết quả thực tế

| Cấu hình | Số chunk | Min / median / max ký tự | Trung bình | Tổng ký tự trong chunks |
|---|---:|---|---:|---:|
| A | 188 | 58 / 500 / 500 | 447.38 | 84107 |
| B | 206 | 48 / 416.5 / 500 | 372.36 | 76707 |
| C | 206 | Dùng đúng file B | Như B | Không lưu bản sao |

- A có thêm 7.400 ký tự do overlap; B không overlap và tổng ký tự bằng 76.707 ký tự corpus. Không suy luận chất lượng truy xuất từ số chunk.
- Đầu ra: `results/chunks_A.jsonl`, `results/chunks_B.jsonl`, `results/chunking_stats.json`.
- Thời gian lưu trong stats chỉ đo tạo chunk và kiểm tra bao phủ, chưa gồm ghi file, embedding hoặc ingest database. Chưa có tokenizer/model để báo số token hay chi phí embedding.

### Kiểm tra và minh chứng

- `starter/.venv/bin/python starter/scripts/prepare_chunks.py` từ root: chạy thành công.
- `.venv/bin/python scripts/prepare_chunks.py` từ `starter/`: chạy thành công, checksum hai file chunk giống lần chạy từ root, không append hoặc nhân đôi.
- `starter/.venv/bin/python -m unittest discover -s starter/tests -v`: **43 tests đạt** (34 cũ + 9 chunking).
- Trên corpus thật: tất cả ký tự của 40 trang đều được bao phủ trong cả A và B; mọi chunk là đúng lát text theo offset, tối đa 500 ký tự và giữ metadata chương.
- Không có ID trùng trong từng bộ chunk. C trỏ đúng cùng file B. Cả hai cách chunk bao phủ đầy đủ 10 anchor coherence đã khóa.
- SHA-256 A: `cfd66c7663581c080d11704cae58dca188e9bb1520d50767cc61f6219a5e8d8e`.
- SHA-256 B/C: `4734495cdb1d44538efedb93129feeeec34494e037adb95007a1c8d1c87e0ddc`.
- Kiểm tra lại thống kê với file xuất và checksum cấu hình: khớp. Snapshot corpus/benchmark không đổi.

### Trạng thái và giới hạn

- **Đạt checkpoint 1:50:** đã có đọc/chuẩn hóa, log lỗi/rỗng, metadata truy nguồn và xuất hai cấu hình chunk.
- Chia theo đoạn chỉ giữ cấu trúc khi phù hợp giới hạn; dòng/đoạn quá dài vẫn có thể bị cắt ý hoặc code. Chưa tự gán điểm coherence; sẽ audit theo GUIDE sau khi chạy.
- Chưa có embedding thật, vector store, top-3 retrieval hoặc kiểm tra nạp lại vector. Việc file chunk chạy lại không đổi không thay thế minh chứng idempotency của vector store.
- Bước tiếp theo là chọn một model thật, kiểm tra giới hạn token và triển khai lưu/truy xuất vector để tiến tới checkpoint 2:40.
- Chưa sửa `run.py` thành pipeline hoàn chỉnh; các lệnh theo giai đoạn ở đầu changelog là cách chạy hiện hành. Chưa commit/push.
- Trong lúc triển khai, phát hiện `STUDENT.md` có chỉnh sửa thông tin học viên ngoài các thao tác của trợ lý. Giữ nguyên chỉnh sửa đó; không tự điền hoặc sửa tài liệu. Kiểm tra whitespace phần code đạt; kiểm tra toàn repo còn báo trailing whitespace ở dòng chủ đề của STUDENT, không phải thay đổi do bước chunking tạo ra.

## 2026-11-14 — Đọc lại docs và đối chiếu hướng triển khai

### Nội dung docs/README.md đã xác minh

- Tài liệu trong `docs/` hiện chỉ có `README.md`.
- Chọn một embedding model thật và một vector store; giữ cùng model/store/cosine cho A/B/C. Ghi phiên bản, cách xử lý query/document, số chiều, cách chạy, đường dẫn/index và chi phí.
- Embedding có thể qua API hoặc local; Sentence Transformers/model MiniLM trong docs là ví dụ, không phải model bắt buộc. Yêu cầu model EmbeddingGemma2 của người dùng chưa bị thay đổi.
- PostgreSQL/pgvector, Qdrant và Chroma đều là lựa chọn được cho phép. Store phải lưu bền vững, tìm kiếm vector và filter metadata; không dùng mode chỉ trong RAM.
- Không dùng vector mock thay model thật; không âm thầm đổi model hoặc backend khi lỗi. Phải ghi phần chưa chạy và giới hạn.

### Việc đã làm trong lần triển khai bị ngắt trước đó

- Dùng `google/embeddinggemma-2`, revision `f9972ac22e696a105c482202646979e33e4b5a1e`, chế độ text-only CPU float32, 768 chiều; đã tắt encoder vision/audio.
- Tham khảo model card chính thức Google, cấu hình prompt của model trên Hugging Face và tài liệu Transformers. Query dùng search prefix; document dùng tiêu đề thật và text. Kiểm tra token trước khi encode, không truncate âm thầm; vector hữu hạn, L2-normalized.
- Đã cài dependency và tải trọng số; lưu trọng số trong `starter/.venv/model_cache`, được Git bỏ qua. Phiên bản cài thực tế nằm ở `results/environment.txt`; dependency bổ sung nằm trong `starter/requirements-embedding.txt`, không thay requirements gốc.
- Docker bị hệ điều hành từ chối quyền socket cả khi thử ngoài sandbox; không thay quyền máy. Đã chuyển dự kiến lưu trữ sang Qdrant local và thông báo trong hội thoại. Người dùng sau đó yêu cầu dừng để đọc lại docs, nên lựa chọn backend đang được làm rõ, không tự tiếp tục đổi sang phương án khác.
- Mã hiện tại: `starter/src/embeddings.py` (adapter), `starter/src/store.py` (Qdrant local), `starter/src/run.py` (ingest/search); cấu hình tại `starter/model_config.json`.
- Sửa import `scripts.validate_benchmark` để script chunk dùng được cả trực tiếp lẫn khi import vào module pipeline. Thêm regression test CLI.
- Các lỗi khởi tạo thực tế đã gặp: import module, thiếu Pillow, thiếu Torchvision của processor. Đã bổ sung dependency CPU tương thích; log được giữ ở `results/runtime_errors.jsonl`. Không ghi lỗi thành kết quả truy xuất rỗng.
- Đã chạy **48 tests đạt**, `pip check` không phát hiện dependency lỗi. Tests store dùng vector fixture cố định chỉ để kiểm tra backend; ingest thật dùng đúng model, không dùng fixture làm số liệu.

### Kết quả thực tế đã lưu, không phải benchmark

| Cấu hình | Chunks/vector | Embedding (giây) | Ghi store lần đầu (giây) | Kiểm tra nạp lại |
|---|---:|---:|---:|---|
| A | 188 | 100.818 | 0.317 | Vẫn 188 điểm |
| B | 206 | 137.506 | 0.427 | Vẫn 206 điểm |
| C | 206 | Dùng lại B | Dùng lại B | Cùng collection B |

- Thực tế có hai collection vật lý cho ba cấu hình logic; không gọi đây là ba collection độc lập. C chỉ khác filter.
- Model đã tải `271002624` tham số text; kiểm tra float32 và tắt modality không dùng đã đạt.
- Đã encode 394 document inputs, token dài nhất 238 (kể cả định dạng/prompt), dưới giới hạn kiểm tra 8192.
- Paid API cost: 0 USD; chưa tính điện và phần cứng local. Thời gian model load, embedding và ghi store tách riêng; không coi đây là tốc độ truy vấn hoặc benchmark tổng thể.
- `results/vector_smoke.json` chỉ là một câu kiểm tra setup chưa chấm điểm, top-3 cho A/B/C; C lọc chương 2 theo input đã cung cấp.
- `results/vector_ingestion_stats.json` ghi model/revision, thư viện, số chiều, collection, thời gian, số điểm, token và kiểm tra persistence. Đã đóng/mở lại store và đối chiếu số điểm/kết quả.

### Sửa sự thiếu nhất quán và kiểm tra trong lần rà soát này

- Sửa trạng thái ở đầu changelog: bỏ câu “chưa có embedding/vector search” đã lỗi thời. Không sửa lại lịch sử cũ để xóa các thử nghiệm hoặc lỗi đã xảy ra.
- Kiểm tra trực tiếp database trên đĩa: A=188, B=206, C=206; B/C cùng collection. Config, revision và phiên bản thư viện khớp với stats; signature tương ứng với model, corpus và chiến lược.
- Snapshot corpus/benchmark vẫn đúng checksum. Chưa chạy 15 dev/5 test, chưa có Hit@1/Hit@3 thực nghiệm hoặc nhãn audit.
- Đã hỏi người dùng làm rõ hướng cần đổi, vì docs cho phép nhiều lựa chọn và không chỉ định riêng PostgreSQL hoặc API. Không suy diễn đổi EmbeddingGemma2 thành Gemini/MiniLM hoặc xóa kho hiện có khi chưa xác định đúng ý.
- Không sửa `docs/README.md`, README/requirements gốc hoặc thông tin học viên; chỉ chỉnh code/cấu hình phục vụ triển khai và ghi chú trong changelog.

## 2026-11-14 — Chuyển sang MiniLM và PostgreSQL/pgvector theo yêu cầu

### Đã thực hiện và lý do

- Người dùng đã chọn PostgreSQL/pgvector của starter, sau đó đổi model sang `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Giữ lựa chọn database này; không tiếp tục Qdrant. Người dùng đã khởi động PostgreSQL bằng Docker Compose.
- `starter/model_config.json` pin revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, CPU float32, 384 chiều, batch 16, giới hạn 128 token tính cả special tokens. Query/document dùng text thuần, không còn prompt/title của Gemma.
- `starter/src/embeddings.py`: adapter SentenceTransformer kiểm tra đúng model, số chiều, giới hạn chuỗi, dtype, đầu vào không rỗng, vector hữu hạn và L2-normalized; từ chối input quá dài thay vì cắt mất nội dung.
- `starter/src/chunking.py` và `starter/scripts/prepare_chunks.py`: giữ cách chia A/B đã chọn, chia thêm đoạn vượt giới hạn bằng tokenizer đúng revision, giữ offsets và metadata, kiểm tra không mất ký tự nội dung. Đây là điều chỉnh theo giới hạn model trước benchmark, không dựa vào điểm dev/test. C dùng nguyên chunks/vector B.
- `starter/src/store.py`: thay backend bằng psycopg/pgvector, truy vấn cosine exact, filter chapter bằng tham số SQL; upsert snapshot trong transaction, xóa chunk lỗi thời trong đúng namespace/strategy, nạp lại không trùng. C ánh xạ sang B. Kiểm tra chiều cột vector để tránh trộn model.
- `starter/src/run.py`: ingest/search thật, namespace theo cấu hình/corpus/thư viện; đo thời gian embedding và ghi database riêng, kiểm tra top-3/filter, đóng/mở lại kết nối và đối chiếu kết quả. Không dùng vector giả thay model thật.
- `starter/requirements-embedding.txt` bỏ dependency trực tiếp của Qdrant/Gemma; không sửa requirements, Docker Compose hoặc tài liệu gốc. Môi trường local còn một số dependency của thử nghiệm cũ; danh sách cài thực tế được lưu để phân biệt với dependency tối thiểu.
- Lưu kết quả Gemma2/Qdrant cũ vào `results/archive/embeddinggemma2_qdrant/`, không dùng chúng làm kết quả MiniLM. Sửa phần hướng dẫn hiện hành ở đầu changelog; các mục lịch sử phía trên mô tả trạng thái tại thời điểm đó.

### Nguồn kỹ thuật đã đối chiếu

- [Model card chính thức MiniLM](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2): SentenceTransformer, vector 384 chiều, mean pooling và max sequence length 128. Giữ cấu hình model gốc.
- [Tài liệu pgvector chính thức](https://github.com/pgvector/pgvector): toán tử `<=>` là cosine distance; dùng `1 - distance` để trả similarity. Không tạo ANN index cho bộ dữ liệu nhỏ hiện tại.
- [Psycopg parameter binding](https://www.psycopg.org/psycopg3/docs/basic/params.html): truyền giá trị bằng placeholder, không nội suy nội dung truy vấn/filter vào SQL.

### Kiểm tra và kết quả thực tế

- PostgreSQL **16.16**, pgvector **0.8.7** kết nối thành công; `HF_HUB_OFFLINE=1 .venv/bin/python -m src.run ingest` hoàn tất với model local đã tải.
- A: **244** chunks/vector; B: **229**; C: **229**, dùng lại B. Có hai phân vùng dữ liệu A/B trong bảng `day6_chunks`, phục vụ ba chiến lược logic; không coi C là một bộ vector độc lập.
- Đã encode **473** document inputs bằng model thật, token dài nhất **128**, tham số tải **117653760**, dtype float32. Đã kiểm tra không mất nội dung và offsets khớp trang nguồn.
- A: embedding **11.456 giây**, ghi store lần đầu **0.125 giây**; B: embedding **12.000 giây**, ghi store **0.097 giây**. Model load **6.540 giây**. Đây là thời gian lần chạy setup trên máy hiện tại, không phải benchmark tốc độ tổng thể.
- Upsert lần hai vẫn A=244/B=229; đóng/mở lại kết nối giữ nguyên số lượng và top-3/score. C trả đúng chapter 2 cho câu smoke chưa chấm điểm. Chi phí paid API **0 USD**, chưa tính phần cứng/điện.
- **50/50 tests đạt**, gồm cả bốn kiểm thử PostgreSQL thật (bật `RUN_PGVECTOR_TESTS=1`), không có test bị skip. Kiểm tra gồm cosine/filter, nạp lại, xóa chunk lỗi thời, persistence và giới hạn token/offsets.
- `validate_benchmark.py` đạt: 20 câu, 15 dev/5 test, 24 evidence spans, 10 coherence samples; snapshot frozen giữ nguyên, re-extract PDF xác minh evidence. `pip check` không phát hiện dependency lỗi.
- Bằng chứng: `results/chunking_stats.json`, `results/vector_ingestion_stats.json`, `results/vector_smoke.json`, `results/benchmark_validation.json`.
- Chạy thêm CLI search từ một tiến trình Python mới: cả A/B/C giữ nguyên top-3 IDs và score so với smoke; C vẫn chỉ trả chapter 2. Minh chứng: `results/fresh_process_search_check.json`. Lưu môi trường thực tế tại `results/environment.txt`; `git diff --check -- starter` đạt, không còn tham chiếu Gemma/Qdrant trong code/cấu hình/dependency/test hiện hành.

### Trạng thái checkpoint và việc tiếp theo

- Đã có minh chứng cho mốc **2:40**: A/B/C truy xuất top-3, model/tham số/thời gian/chi phí và kiểm tra nạp lại. C thực hiện đúng B + filter; không nhân đôi vector chỉ để tạo ba kho vật lý.
- Chưa hoàn thành mốc **3:30**: chưa có benchmark dev/test, Hit@1/Evidence Hit@3 thực nghiệm hoặc nhãn coherence/metadata/grounding. Tiếp theo chạy đánh giá theo protocol frozen và audit, không dùng câu smoke làm kết quả benchmark.

## 2026-11-14 — Hoàn tất benchmark, audit có khai báo AI và báo cáo cá nhân

### Đã thực hiện

- Thêm `starter/src/benchmarking.py` và command `benchmark --split dev|test` vào `starter/src/run.py`. Query chỉ dùng câu hỏi; C chỉ nhận chapter trong input, A/B không filter. Mỗi query encode một lần, dùng chung vector giữa ba chiến lược, top-k=3, exact cosine.
- Chạy **15 dev × 3 = 45 trace**, lưu `results/retrieval_dev.jsonl` và `retrieval_metrics_dev.json`. Trước mọi truy xuất test, tính lại metric dev, áp dụng đúng tiêu chí protocol, ghi `results/dev_selection.json` với lựa chọn B và checksum code/config/chunks/dev outputs.
- Khóa lựa chọn lúc `2026-11-14T05:00:53.613036+00:00`; bắt đầu test lúc `2026-11-14T05:00:53.625824+00:00`. Chạy **5 test × 3 = 15 trace**, lưu `results/retrieval_test.jsonl` và `retrieval_metrics_test.json`. Không đổi model/corpus/chunking/filter/gold sau khi xem test.
- Thêm `starter/scripts/prepare_audits.py`: chọn chunk theo 10 anchors frozen, tạo packet coherence/grounding/metadata; re-extract PDF cho mọi trang trong top-3 test. Script không tạo nhãn semantic.
- Codex trực tiếp đọc 20 chunk A/B khác nhau, 15 top-3 test traces và đối chiếu 45 bản ghi metadata; ghi 30/15/45 nhãn cùng lý do tại `results/audit_labels.json`. C coherence kế thừa đúng chunk B, không coi là mẫu độc lập mới. **Reviewer là AI, chưa có xác nhận con người; không gọi đây là audit do học viên đã tự chấm.**
- Thêm `starter/scripts/summarize_results.py`: kiểm tra đủ ma trận, rescore trace, kiểm tra lock/thời điểm chọn, đồng nhất B/C khi không filter, nhãn gắn đúng packet/ID và tổng hợp tử/mẫu. Tạo `results/retrieval_metrics.json`, `audit_summary.json`, `run_validation.json`; không tự relabel hoặc gọi model.
- Điền **dữ liệu thí nghiệm đúng mục đích** vào `artifacts/experiment_log.csv`: cấu hình, giả thuyết thiết kế, số đo, nguồn/giới hạn log. CSV ghi sau chạy, không giả nhận giả thuyết đã preregister riêng. Không dùng tệp này để thêm ghi chú tiến độ ngoài mục đích.
- Tạo báo cáo mới `report/individual/2A202604019_LaiTrongDuc.md` theo cấu trúc mẫu, không sửa mẫu gốc. Báo cáo có năm khía cạnh, bảng thời gian/chi phí, lý do chọn B, ví dụ lỗi q18/q19/q20, nguồn/quyền, AI disclosure, giới hạn và lệnh tái lập.
- Bổ sung ba kiểm thử chọn chiến lược: ưu tiên đúng dev Hit@3, C chịu đầy đủ ingest cost B, từ chối dữ liệu test/không đủ khi chọn.

### Kết quả đo thật

| Strategy | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 | Filter dev / test |
|---|---|---|---|---|---|
| A | 3/15 | 7/15 | 2/5 | 2/5 | 1/2 · 1/2 |
| B | 7/15 | 11/15 | 2/5 | 3/5 | 1/2 · 0/2 |
| C | 7/15 | 11/15 | 2/5 | 3/5 | 2/2 · 2/2 |

- B/C hòa dev metrics, cùng ingest cost/chunk count; B được chọn theo alphabet tie-break đã frozen. Không dùng test để đổi sang C.
- Nhãn AI-reviewed: coherence A **1,0/2**, B/C **1,8/2** (10 vị trí); metadata **15/15 mỗi cấu hình**; grounding **0/1/2 = 2/0/3**, mean **1,2/2** cho mỗi cấu hình. Tất cả có lý do từng trường hợp và reviewer/method, trạng thái human confirmation pending.
- C lọc đúng nhưng không tăng hit trong mẫu này. B/C giống hệt nhau cho **16 câu không filter**. A/B chủ đích không filter, nên không gọi số tuân thủ thấp là lỗi backend.
- q18-A minh họa đúng trang nhưng gold bị cắt; grounding top-3 đủ về ý nhưng metric single-chunk không hit. q19/q20 thiếu get/default và reverse-lookup trong top-3 ở cả ba cấu hình. Giữ nguyên miss, không bù bằng kiến thức ngoài trace hoặc sửa gold sau test.
- Đã phát hiện fragment rất ngắn khi giới hạn token chia lại cửa sổ (A ngắn nhất một ký tự, B năm ký tự); báo cáo hạn chế, không chỉnh chunk sau khi xem test. Không mặc nhiên coi metadata đúng là evidence đủ.

### Kiểm tra và phạm vi hoàn thành

- **53/53 tests đạt**, không skip, gồm bốn kiểm thử PostgreSQL thật. Bộ tổng hợp xác minh đủ **60 trace / 180 hits**, **30 coherence / 15 grounding / 45 metadata records**, source spans khớp exports, snapshot không đổi và selection lock đúng trước test.
- Re-extract bảy trang test có trong trace (111/112/113/114/125/126/128); không phát hiện lệch text/header/trang in hay metadata trong mẫu.
- Kiểm tra cuối lưu tại `results/test_run.txt` và `results/submission_check.json`: 53 tests đạt, 21 liên kết nội bộ trong báo cáo hợp lệ, ba dòng experiment log khớp metric, `git diff --check` đạt cho các file triển khai/nộp bài đã sửa. Sửa writer CSV dùng LF thay CRLF để không tạo cảnh báo whitespace; không thay số liệu. `pip check` đạt. Quét 84 text files theo mẫu key phổ biến không có kết quả đáng ngờ; `.env`/virtualenv/model cache được Git bỏ qua. Đây không phải chứng nhận secret scan tuyệt đối.
- Code vẫn trong `starter/`. Không sửa README, docs, đề bài, requirements/Docker Compose gốc hoặc mẫu báo cáo. Điền đúng trường chủ đề/corpus còn trống của `STUDENT.md` bằng chủ đề đã triển khai để hoàn thiện thông tin nộp bài; giữ nguyên tên/MSSV/lớp/repo do người dùng cung cấp và `.vscode/`. Không thêm ghi chú tiến độ vào STUDENT.md; trường commit chốt bài vẫn trống vì chưa commit.
- Phần triển khai, chạy benchmark và soạn artifacts/báo cáo đã hoàn tất ở local. Mốc **3:30** có số liệu và nhãn AI hỗ trợ; yêu cầu audit thủ công cần học viên đọc/xác nhận. Mốc **4:00** đã có báo cáo và cấu trúc file; **chưa commit/push/nộp link**, chưa điền commit chốt bài của STUDENT.md. Không tự khai đã làm phần cần học viên xác nhận hoặc xuất bản.

## 2026-11-14 — Kiểm tra trước khi công bố và merge main

- Người dùng yêu cầu chốt toàn bộ bài, push nhánh triển khai và merge vào `main`; đây là bước xuất bản đã được cho phép trong phiên làm việc.
- Kiểm tra lại **53/53 tests**, gồm PostgreSQL thật, cùng validator evidence/PDF và bộ tổng hợp kết quả: đều đạt. Frozen corpus/benchmark và selection lock không đổi; không chỉnh model/chunking theo test.
- Đồng bộ refs từ `origin`, kiểm tra quyền repository và đối chiếu main trước khi push. Chỉ stage dữ liệu/code/artifacts/báo cáo phục vụ bài nộp; giữ `.vscode/` cá nhân, `.env`, virtualenv, model cache và database local ngoài commit.
- Giữ khai báo audit do AI đánh giá và trạng thái human confirmation pending. Việc cho phép push/merge không được diễn giải thành việc học viên đã đọc/chấm các nhãn.
- Sau merge sẽ ghi SHA merge thật vào STUDENT.md và cập nhật trạng thái phát hành trong báo cáo/changelog; không tự ghi SHA dự đoán hoặc tuyên bố đã nộp bài qua kênh của lớp.

## Mẫu cho lần cập nhật tiếp theo

Khi có thay đổi mới, thêm mục ngày và tên công việc phía trên mẫu này, theo cấu trúc:

```text
## YYYY-MM-DD — Tên công việc

### Đã thực hiện
- File/hàm và thay đổi cụ thể.

### Lý do
- Yêu cầu được đáp ứng hoặc vấn đề được giải quyết.

### Kiểm tra và kết quả
- Lệnh/cách kiểm tra, kết quả thực tế và đường dẫn bằng chứng.

### Tồn tại và việc tiếp theo
- Phần chưa hoàn thành, giới hạn hoặc lỗi còn gặp nếu có.
```
