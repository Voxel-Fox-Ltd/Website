CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "citext";


CREATE TABLE IF NOT EXISTS google_forms_redirects(
    form_id VARCHAR(100) NOT NULL,
    alias VARCHAR(100),
    username_field_id VARCHAR(100),
    user_id_field_id VARCHAR(100)
);


CREATE TABLE IF NOT EXISTS users(
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- The user who the account belongs to
    discord_user_id BIGINT UNIQUE NOT NULL,

    -- IDs for other services
    stripe_id TEXT,
    paypal_id TEXT,

    -- API keys for payments
    stripe_api_key TEXT,
    stripe_webhook_signing_secret TEXT,
    paypal_client_id TEXT,
    paypal_client_secret TEXT
);


CREATE TABLE IF NOT EXISTS checkout_items(
    id UUID NOT NULL DEFAULT uuid_generate_v4(),

    -- The person who created this item
    creator_id UUID NOT NULL REFERENCES users(id),

    -- Product information
    product_name CITEXT NOT NULL,
    subscription BOOLEAN NOT NULL DEFAULT FALSE,
    success_url TEXT NOT NULL DEFAULT 'http://localhost',
    cancel_url TEXT NOT NULL DEFAULT 'http://localhost',

    -- Information on the product IDs
    stripe_product_id TEXT NOT NULL,
    stripe_price_id TEXT NOT NULL,
    paypal_plan_id TEXT,

    -- Webhooks to send to when there's a purchase been made
    transaction_webhook TEXT,
    transaction_webhook_authorization TEXT NOT NULL DEFAULT '',

    -- When this page is fetched, products from the same group will be shown
    -- together if there is one. If no group, then the product will not appear
    -- on a page.
    product_group TEXT,

    -- Whether or not the product is per guild (true) or per user (false). Only
    -- applies to purchases done through this site; not to externals.
    per_guild BOOLEAN NOT NULL DEFAULT FALSE,

    -- Whether or not the product can be purchased multiple times. Ignored if
    -- the product is a subscription.
    multiple BOOLEAN NOT NULL DEFAULT FALSE,

    -- Text to be displayed on the portal page.
    description TEXT
);


-- A transaction log for purchases made through the website. Doesn't check
-- validity, but rather just a log of income.
CREATE TABLE IF NOT EXISTS transactions(
    id UUID NOT NULL DEFAULT uuid_generate_v4(),

    -- The item that was purchased
    product_id UUID NOT NULL REFERENCES checkout_items(id),

    -- The amount of the purchase
    amount_gross INTEGER NOT NULL,
    amount_net INTEGER,
    currency VARCHAR(3) NOT NULL,

    -- The amount that actually goes into the user's account
    settle_amount INTEGER NOT NULL,
    settle_currency VARCHAR(3) NOT NULL,

    -- The transaction ID from the payment processor
    identifier TEXT NOT NULL,

    -- The payment processor that was used
    payment_processor TEXT NOT NULL,

    -- Timestamp of purchase
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Information about the purchase and the purchaser
    customer_email CITEXT,
    metadata TEXT
);


-- A table holding references to the products that a user has purchased.
-- Only contains ACTIVE purchases - non-refunded purchases, active
-- subscriptions, etc. This table should not be used as a reference for
-- income.
CREATE TABLE IF NOT EXISTS purchases(
    id UUID NOT NULL PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- The product that was purchased
    product_id UUID NOT NULL REFERENCES checkout_items(id),

    -- The user who purchased the item
    discord_user_id BIGINT NOT NULL,
    discord_guild_id BIGINT,

    -- If the item is a subscription, cancel metadata
    cancel_url TEXT,
    expiry_time TIMESTAMP,  -- If cancelled, when the subscription expires

    -- Timestamp of purchase
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- Create some indexes for easier searching
CREATE INDEX IF NOT EXISTS
    purchases_user_id_product_name_expiry_time_idx
    ON purchases
    (user_id, product_id, expiry_time);
CREATE INDEX IF NOT EXISTS
    purchases_guild_id_product_name_expiry_time_idx
    ON purchases
    (guild_id, product_id, expiry_time);
