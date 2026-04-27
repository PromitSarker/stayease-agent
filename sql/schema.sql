CREATE TABLE IF NOT EXISTS listings (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    photos TEXT[] NOT NULL DEFAULT '{}',
    house_rules TEXT[] NOT NULL DEFAULT '{}',
    host_name TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    price_per_night INTEGER NOT NULL CHECK (price_per_night > 0),
    max_guests INTEGER NOT NULL CHECK (max_guests > 0),
    amenities TEXT[] NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_listings_location_lower
    ON listings (LOWER(location));

CREATE INDEX IF NOT EXISTS idx_listings_active
    ON listings (is_active);

CREATE TABLE IF NOT EXISTS bookings (
    id BIGSERIAL PRIMARY KEY,
    booking_code TEXT UNIQUE NOT NULL,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    guest_name TEXT NOT NULL,
    guest_phone TEXT NOT NULL,
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    num_guests INTEGER NOT NULL CHECK (num_guests > 0),
    total_price_bdt INTEGER NOT NULL CHECK (total_price_bdt >= 0),
    status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (status IN ('confirmed', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_booking_dates CHECK (check_out > check_in)
);

CREATE INDEX IF NOT EXISTS idx_bookings_listing_dates
    ON bookings (listing_id, check_in, check_out);

CREATE INDEX IF NOT EXISTS idx_bookings_status
    ON bookings (status);

CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    intent TEXT CHECK (intent IN ('search', 'details', 'book', 'escalate')),
    escalate BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_conversation_id
    ON conversations (conversation_id, created_at);
