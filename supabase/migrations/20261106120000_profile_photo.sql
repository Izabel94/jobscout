-- CV photo, uploaded from the Settings tab. Stored on the profile (base64 JPEG,
-- resized to <= 600x800, ~70 KB) so every machine that renders a CV — the apply
-- worker on the user's PC and Streamlit Cloud — gets the same photo.
alter table profiles add column if not exists photo_jpeg_b64 text;
