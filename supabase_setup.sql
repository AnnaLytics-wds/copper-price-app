-- 在 Supabase 的 SQL Editor 里运行一次即可。

create table if not exists copper_prices (
  id bigserial primary key,
  date date unique not null,
  price numeric not null
);

alter table copper_prices enable row level security;

-- 可重复执行：先删旧策略再重建，避免第二次运行报错。
drop policy if exists "允许公开读取铜价" on copper_prices;
drop policy if exists "允许应用写入铜价" on copper_prices;
drop policy if exists "允许应用更新铜价" on copper_prices;

create policy "允许公开读取铜价"
  on copper_prices for select using (true);

create policy "允许应用写入铜价"
  on copper_prices for insert with check (true);

-- upsert 更新已有日期时还需要 UPDATE 权限，缺少这条会导致重复点击时报权限错误。
create policy "允许应用更新铜价"
  on copper_prices for update using (true) with check (true);
