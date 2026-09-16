-- ===========================================================================
-- Chatbot Văn Phú - lược đồ cơ sở dữ liệu
-- Chạy toàn bộ file này một lần trong Supabase Dashboard > SQL Editor.
-- Sau đó tạo bucket PUBLIC tên 'media' trong Storage để chứa ảnh/poster.
-- ===========================================================================

create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- documents: các đoạn tri thức đã embedding
--   source = 'qa'            -> cặp hỏi/đáp từ sheet Q&A
--   source = 'units_summary' -> tóm tắt layout/thống kê căn hộ, shophouse
--   source = 'media'         -> mô tả ảnh/poster/link (URL nằm trong metadata)
-- ---------------------------------------------------------------------------
create table if not exists documents (
  id         uuid primary key,
  source     text not null,
  section    text,
  title      text,
  content    text not null,
  metadata   jsonb not null default '{}'::jsonb,
  embedding  vector(768) not null,
  created_at timestamptz not null default now()
);

create index if not exists documents_embedding_hnsw
  on documents using hnsw (embedding vector_cosine_ops);
create index if not exists documents_source_idx on documents (source);

-- ---------------------------------------------------------------------------
-- match_documents: tìm kiếm ngữ nghĩa theo cosine similarity
--   filter_sources = null  -> tìm trong tất cả nguồn
--   filter_sources = '{qa,units_summary}' -> giới hạn theo nguồn
-- ---------------------------------------------------------------------------
create or replace function match_documents(
  query_embedding vector(768),
  match_count     int    default 6,
  filter_sources  text[] default null
)
returns table (
  id         uuid,
  source     text,
  section    text,
  title      text,
  content    text,
  metadata   jsonb,
  similarity float
)
language sql
stable
as $$
  select
    d.id,
    d.source,
    d.section,
    d.title,
    d.content,
    d.metadata,
    1 - (d.embedding <=> query_embedding) as similarity
  from documents d
  where filter_sources is null or d.source = any(filter_sources)
  order by d.embedding <=> query_embedding
  limit match_count;
$$;

-- ---------------------------------------------------------------------------
-- units: giỏ hàng căn hộ / shophouse (dữ liệu có cấu trúc, tra cứu chính xác)
--   is_primary   = dòng mang số thứ tự (mỗi căn đúng 1 dòng)
--   is_total_row = dòng tổng hợp nhiều tầng ('1+2' của shophouse, '34+35' của PH)
-- ---------------------------------------------------------------------------
create table if not exists units (
  id                   bigint generated always as identity primary key,
  project_code         text not null default '03HNCM008',
  unit_code            text,          -- 'A-06-01' (theo bản vẽ thi công)
  unit_code_alt        text,          -- 'A-NN-01' (theo BVTĐ-GPXD)
  unit_code_commercial text,          -- 'CH-A06-01' / 'PH-B34-01' / 'SH-A01-01' / 'TM-A03-09'
  tower                text,          -- 'A' | 'B'
  floor                int,           -- null với dòng tổng hợp ('1+2')
  floor_label          text,          -- giữ nguyên giá trị gốc: '6', '1+2', '34+35'
  unit_no              text,          -- '01', '02', ...
  product_type         text not null, -- 'CH' | 'PH' | 'SH' | 'TM'
  area_gross           numeric(8,2),  -- diện tích tim tường
  area_net             numeric(8,2),  -- diện tích thông thủy
  bedrooms             text,          -- giá trị gốc: '3BR', '1BR+1'
  bedroom_count        smallint,      -- đã tách số: 3, 1
  balcony_dir          text,
  door_dir             text,
  note                 text,
  is_primary           boolean not null default true,
  is_total_row         boolean not null default false,
  sheet_row            int,           -- số dòng trong file Excel gốc (truy vết)
  sheet_name           text
);

create index if not exists units_code_idx on units (unit_code);
create index if not exists units_code_commercial_idx on units (unit_code_commercial);
create index if not exists units_code_alt_idx on units (unit_code_alt);
create index if not exists units_filter_idx
  on units (product_type, tower, floor, bedroom_count);

-- ---------------------------------------------------------------------------
-- Bảo mật: bật RLS và KHÔNG tạo policy nào.
-- Backend dùng secret key (service role) nên vẫn đọc/ghi được;
-- anon key hoặc người lạ không truy cập được dữ liệu.
-- ---------------------------------------------------------------------------
alter table documents enable row level security;
alter table units     enable row level security;
