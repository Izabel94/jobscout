-- Favorite/bookmark toggle for listings.
alter table listings add column if not exists bookmarked boolean not null default false;
create index if not exists listings_bookmarked_idx on listings (bookmarked) where bookmarked;
