# Phân loại ý định tiếng Việt trong môi trường có ngữ cảnh

Đồ án môn học 3 – Đỗ Thanh Sơn (SoICT, ĐH Bách Khoa Hà Nội). GVHD: TS. Tưởng Văn Đạt.

So sánh phân loại ý định (intent) khi chỉ dùng câu hiện tại và khi thêm lịch sử hội thoại:
(A) TF-IDF + Logistic Regression, (B) PhoBERT không ngữ cảnh, (C) PhoBERT có ngữ cảnh.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Cấu trúc

```
data/raw/        dữ liệu gốc tải về, không sửa
data/interim/    dữ liệu đang xử lý
data/processed/  train/val/test cuối cùng
notebooks/       khám phá, thử nghiệm
src/             mã nguồn chính
scripts/         lệnh chạy từng thí nghiệm
models/          mô hình đã huấn luyện (không đưa lên Git)
reports/figures/ biểu đồ, kết quả
docs/            tài liệu môn học, báo cáo tuần
```
