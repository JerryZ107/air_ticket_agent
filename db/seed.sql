-- 种子数据：密码均为 demo123（bcrypt rounds=12）
-- 生成：python -c "import bcrypt; print(bcrypt.hashpw(b'demo123', bcrypt.gensalt(12)).decode())"

INSERT INTO users (id, username, password_hash, display_name, role) VALUES
    ('11111111-1111-1111-1111-111111111101', 'zhangsan',
     '$2b$12$bw4KrhZKirYUttoCs6WO7..EiuuAD8.GIA.lfgBbB/oVU21lN2QiO', '张三', 'user'),
    ('11111111-1111-1111-1111-111111111102', 'lisi',
     '$2b$12$bw4KrhZKirYUttoCs6WO7..EiuuAD8.GIA.lfgBbB/oVU21lN2QiO', '李四', 'user'),
    ('11111111-1111-1111-1111-111111111199', 'admin',
     '$2b$12$bw4KrhZKirYUttoCs6WO7..EiuuAD8.GIA.lfgBbB/oVU21lN2QiO', '管理员', 'admin')
ON CONFLICT (username) DO NOTHING;

INSERT INTO flights (id, flight_no, origin, destination, departure_at, arrival_at, seats_total, seats_available, price_cents, status) VALUES
    ('22222222-2222-2222-2222-222222222201', 'PA441', 'Paris (CDG)',   'New York (JFK)', '2026-08-01 10:00:00+00', '2026-08-01 13:00:00+00', 120, 45, 45000, 'delayed'),
    ('22222222-2222-2222-2222-222222222202', 'NY802', 'New York (JFK)','Austin (AUS)',   '2026-08-01 16:00:00+00', '2026-08-01 19:00:00+00', 120, 30, 28000, 'scheduled'),
    ('22222222-2222-2222-2222-222222222203', 'NY900', 'New York (JFK)','Austin (AUS)',   '2026-08-02 08:00:00+00', '2026-08-02 11:00:00+00', 120, 80, 32000, 'scheduled'),
    ('22222222-2222-2222-2222-222222222204', 'PA500', 'Paris (CDG)',   'Austin (AUS)',   '2026-08-02 06:00:00+00', '2026-08-02 18:00:00+00', 120, 60, 68000, 'scheduled')
ON CONFLICT DO NOTHING;

INSERT INTO bookings (id, user_id, flight_id, confirmation_no, seat, status, price_paid_cents) VALUES
    ('33333333-3333-3333-3333-333333333301', '11111111-1111-1111-1111-111111111101', '22222222-2222-2222-2222-222222222201', 'ABC123', '12A', 'confirmed', 45000),
    ('33333333-3333-3333-3333-333333333302', '11111111-1111-1111-1111-111111111102', '22222222-2222-2222-2222-222222222202', 'XYZ789', '8C',  'confirmed', 28000)
ON CONFLICT (confirmation_no) DO NOTHING;
