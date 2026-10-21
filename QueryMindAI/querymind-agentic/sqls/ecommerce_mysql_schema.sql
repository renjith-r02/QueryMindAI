-- =====================================================================
-- E-COMMERCE ORDERS SCHEMA  (MySQL 8.0+, InnoDB, utf8mb4)   database: ecommerce
-- =====================================================================
-- PURPOSE
--   Relational schema for an online store: customers, product catalog,
--   product price history, orders and order lines.
--   RETURNS ARE NOT IN THIS DATABASE. They live in a separate PostgreSQL
--   database `returns_db`, schema `rma` (tables rma.returns and
--   rma.return_lines; see returns_postgres_schema.sql).
--   Written to be read by humans AND by LLMs that generate SQL
--   (text-to-SQL). Every table and column carries a COMMENT, and this
--   header documents relationships, cross-database links, join paths,
--   business rules and example queries.
--
-- SQL DIALECT: MySQL 8.0. Use MySQL syntax for queries on this database:
--   DATE_FORMAT(), NOW() - INTERVAL 90 DAY, backticks if quoting is needed.
--   Do NOT use PostgreSQL-only syntax here (::casts, FILTER, ILIKE,
--   date_trunc).
--
-- ---------------------------------------------------------------------
-- DATA LOCATION MAP
-- ---------------------------------------------------------------------
--   MySQL `ecommerce` (this file)          PostgreSQL `returns_db`.rma
--   -----------------------------          ---------------------------
--   users, user_addresses                  returns       (RMA header)
--   categories, products                   return_lines  (returned units)
--   product_prices                         v_returned_by_order_line (view)
--   orders, order_lines                    v_return_lines_detail    (view)
--   v_product_current_price (view)
--   v_order_line_sales      (view)
--
-- ---------------------------------------------------------------------
-- TABLE OVERVIEW
-- ---------------------------------------------------------------------
--   users            One row per customer account (registered or guest).
--   user_addresses   Saved shipping/billing addresses of a user (1 user : N addresses).
--   categories       Product category tree (self-referencing via parent_id).
--   products         Sellable items (one row per SKU): name, category, status.
--                    Holds NO price; prices live in product_prices.
--   product_prices   Effective-dated selling-price history per product
--                    (list price and optional sale price, what the CUSTOMER pays).
--   orders           Order header: who bought, when, status, money totals, ship-to snapshot.
--   order_lines      Order detail: one row per product in an order, with price snapshot.
--
-- ---------------------------------------------------------------------
-- RELATIONSHIPS
-- ---------------------------------------------------------------------
--   Inside MySQL (real foreign keys; parent 1 --- N child):
--     users.user_id                    1 --- N  user_addresses.user_id
--     users.user_id                    1 --- N  orders.user_id
--     categories.category_id           1 --- N  categories.parent_id  (tree; NULL = top level)
--     categories.category_id           1 --- N  products.category_id
--     products.product_id              1 --- N  product_prices.product_id
--     products.product_id              1 --- N  order_lines.product_id
--     product_prices.product_price_id  1 --- N  order_lines.product_price_id
--     orders.order_id                  1 --- N  order_lines.order_id
--
--   Cross-database to PostgreSQL returns_db.rma (LOGICAL, NO foreign key;
--   the returns service validates these ids when a return is created):
--     orders.order_id            1 --- N  rma.returns.order_id
--     orders.order_number        1 --- N  rma.returns.order_number   (snapshot)
--     users.user_id              1 --- N  rma.returns.user_id
--     order_lines.order_line_id  1 --- N  rma.return_lines.order_line_id
--     products.product_id        1 --- N  rma.return_lines.product_id (snapshot)
--
-- ---------------------------------------------------------------------
-- ENTITY DIAGRAM (text)
-- ---------------------------------------------------------------------
--   categories --< products --< product_prices
--                    |               |
--                    ^               ^
--   users --< orders --< order_lines -+
--     |         :            :
--     |         :            :          ( ...: = cross-database link to
--     |    rma.returns --< rma.return_lines     PostgreSQL, no FK )
--     |
--     +----< user_addresses
--   ( A --< B  means one A has many B )
--
-- ---------------------------------------------------------------------
-- STANDARD JOIN PATHS (MySQL)
-- ---------------------------------------------------------------------
--   Order with customer:
--     orders o JOIN users u ON u.user_id = o.user_id
--   Order with its items:
--     orders o JOIN order_lines ol ON ol.order_id = o.order_id
--   Items with current catalog data / category:
--     order_lines ol JOIN products p ON p.product_id = ol.product_id
--                    LEFT JOIN categories c ON c.category_id = p.category_id
--   Price row that was applied to an order line:
--     order_lines ol LEFT JOIN product_prices pp ON pp.product_price_id = ol.product_price_id
--   Price valid at a point in time T for a product:
--     product_prices pp ON pp.product_id = p.product_id
--       AND pp.effective_from <= T
--       AND (pp.effective_to IS NULL OR pp.effective_to > T)
--   Current price of a product:
--     product_prices pp ON pp.product_id = p.product_id AND pp.effective_to IS NULL
--   Parent category:
--     categories c JOIN categories parent ON parent.category_id = c.parent_id
--
-- ---------------------------------------------------------------------
-- QUESTIONS THAT INVOLVE RETURNS (cross-database)
-- ---------------------------------------------------------------------
--   A MySQL query CANNOT read PostgreSQL tables. For any question about
--   returns, refunds, return reasons or net revenue after returns:
--     - If the question is ONLY about returns (counts, reasons, refunds,
--       returned SKUs, RMA status): query PostgreSQL alone. rma tables
--       carry order_number, sku, product_name, unit_price snapshots.
--     - If it also needs sales data (return RATE, NET revenue, category,
--       customer name/email): run one query per database, each
--       aggregated to a shared key (order_line_id, order_id, user_id or
--       product_id), then merge the results in application code.
--       Use rma.v_returned_by_order_line on the PostgreSQL side.
--     - If mysql_fdw foreign tables are configured in PostgreSQL
--       (schema ecom), the join can be written as one PostgreSQL query.
--   orders.status and order_lines.status values 'returned' /
--   'partially_returned' are updated by the returns service and only
--   tell WHETHER something was returned, not how many units or how much
--   money; get those from PostgreSQL.
--
-- ---------------------------------------------------------------------
-- BUSINESS RULES AND QUERY GUIDANCE
-- ---------------------------------------------------------------------
--   1. Historical revenue: ALWAYS use order_lines.unit_price (price actually
--      charged, snapshotted at time of sale). Do NOT re-derive it from
--      product_prices for past orders; the snapshot also reflects coupons
--      and manual overrides.
--   2. Current catalog price: product_prices row with effective_to IS NULL.
--      Effective selling price = COALESCE(sale_price, list_price).
--   3. Price at a past moment: product_prices row where
--      effective_from <= T AND (effective_to IS NULL OR effective_to > T).
--      Ranges are half-open [effective_from, effective_to).
--   4. Product name / SKU as sold: use order_lines.product_name and
--      order_lines.sku. Use products.name only for the current catalog.
--   5. Ship-to address of an order: use the ship_* columns on orders, not
--      user_addresses (which the user can edit later).
--   6. Revenue definitions:
--        gross line revenue  = order_lines.line_total
--                            = quantity * unit_price - discount_amount (excl. tax)
--        gross order revenue = SUM(order_lines.line_total)  (= orders.subtotal_amount)
--        net revenue         = gross revenue - refunds   (refunds are in
--                              PostgreSQL rma.v_returned_by_order_line.refunded)
--        orders.total_amount = subtotal_amount - discount_amount
--                              + shipping_amount + tax_amount   (what the customer paid)
--      orders.discount_amount is an ORDER-LEVEL discount (e.g. coupon on the
--      whole basket) in addition to any line-level order_lines.discount_amount.
--   7. Price realization / markdown: order_lines.unit_list_price is the list
--      price at time of sale. Discount from list per unit =
--      unit_list_price - unit_price. Markdown % = 1 - unit_price / unit_list_price.
--   8. Which orders count as sales: exclude orders.status IN ('pending','cancelled')
--      unless the question is explicitly about them. Exclude order_lines.status
--      = 'cancelled'. Orders with status returned/partially_returned ARE
--      sales (they were sold, then returned).
--   9. Dates: orders.placed_at is the sale date for reporting. All DATETIME
--      values are stored in UTC.
--  10. Money: all amounts are in the currency column of the same row
--      (ISO 4217, default USD). Do not add amounts across currencies
--      without conversion.
--  11. Guest checkouts are users with status = 'guest' and password_hash NULL.
--  12. This schema stores selling prices only; it has no product cost, so
--      COGS and profit margin cannot be computed from it.
--
-- =====================================================================

CREATE DATABASE IF NOT EXISTS ecommerce
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;
USE ecommerce;

-- =====================================================================
-- USERS
-- =====================================================================
CREATE TABLE users (
  user_id         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY
                  COMMENT 'Surrogate primary key of the customer. Referenced by orders.user_id, user_addresses.user_id, and (cross-database, no FK) PostgreSQL rma.returns.user_id.',
  email           VARCHAR(255)  NOT NULL
                  COMMENT 'Login and contact email. Unique across all users. Lowercased by the application.',
  password_hash   VARCHAR(255)  NULL
                  COMMENT 'Hashed password (e.g. bcrypt/argon2). NULL for guest checkouts and SSO-only accounts. Never select in analytics.',
  first_name      VARCHAR(100)  NULL
                  COMMENT 'Customer given name.',
  last_name       VARCHAR(100)  NULL
                  COMMENT 'Customer family name.',
  phone           VARCHAR(30)   NULL
                  COMMENT 'Phone number in E.164 format, e.g. +15085551234.',
  status          ENUM('active','inactive','blocked','guest') NOT NULL DEFAULT 'active'
                  COMMENT 'Account state. active = can log in and order; inactive = closed by user; blocked = suspended (fraud/abuse); guest = created by guest checkout without a password.',
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                  COMMENT 'UTC time the account was created (customer signup date; use for cohorts).',
  updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                  COMMENT 'UTC time of the last change to this row.',
  UNIQUE KEY uq_users_email (email),
  KEY idx_users_status_created (status, created_at)
) ENGINE=InnoDB
  COMMENT='Customers. One row per account, including guest checkouts. Parent of orders and user_addresses; referenced by PostgreSQL rma.returns.user_id. Grain: one row per customer.';

-- =====================================================================
-- USER_ADDRESSES
-- =====================================================================
CREATE TABLE user_addresses (
  address_id      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY
                  COMMENT 'Surrogate primary key of the saved address.',
  user_id         BIGINT UNSIGNED NOT NULL
                  COMMENT 'FK -> users.user_id. Owner of this address.',
  label           VARCHAR(50)   NULL
                  COMMENT 'User-given name for the address, e.g. Home, Work.',
  address_type    ENUM('shipping','billing','both') NOT NULL DEFAULT 'both'
                  COMMENT 'Whether the address is used for shipping, billing, or both.',
  line1           VARCHAR(255)  NOT NULL
                  COMMENT 'Street address line 1.',
  line2           VARCHAR(255)  NULL
                  COMMENT 'Apartment, suite, unit (optional).',
  city            VARCHAR(100)  NOT NULL
                  COMMENT 'City or town.',
  state_region    VARCHAR(100)  NULL
                  COMMENT 'State, province or region (e.g. MA).',
  postal_code     VARCHAR(20)   NOT NULL
                  COMMENT 'ZIP or postal code, stored as text to keep leading zeros.',
  country_code    CHAR(2)       NOT NULL
                  COMMENT 'ISO 3166-1 alpha-2 country code, e.g. US, IN, GB.',
  is_default      BOOLEAN       NOT NULL DEFAULT FALSE
                  COMMENT 'TRUE if this is the user''s default address. At most one per user (enforced by the application).',
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                  COMMENT 'UTC time the address was saved.',
  CONSTRAINT fk_addr_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  KEY idx_addr_user (user_id)
) ENGINE=InnoDB
  COMMENT='Saved address book of each user (1 user : N addresses). Current state only; for where an order was actually shipped use the ship_* columns on orders.';

-- =====================================================================
-- CATEGORIES
-- =====================================================================
CREATE TABLE categories (
  category_id     INT UNSIGNED AUTO_INCREMENT PRIMARY KEY
                  COMMENT 'Surrogate primary key of the category.',
  parent_id       INT UNSIGNED  NULL
                  COMMENT 'FK -> categories.category_id (self-reference). NULL = top-level category. Example: Shoes -> Running Shoes.',
  name            VARCHAR(150)  NOT NULL
                  COMMENT 'Display name, e.g. Running Shoes.',
  slug            VARCHAR(150)  NOT NULL
                  COMMENT 'URL-safe unique identifier, e.g. running-shoes.',
  UNIQUE KEY uq_cat_slug (slug),
  KEY idx_cat_parent (parent_id),
  CONSTRAINT fk_cat_parent FOREIGN KEY (parent_id) REFERENCES categories(category_id) ON DELETE SET NULL
) ENGINE=InnoDB
  COMMENT='Product category hierarchy (adjacency list). Join to itself on parent_id for parent/child; use a recursive CTE for full paths. Parent of products.';

-- =====================================================================
-- PRODUCTS
-- =====================================================================
CREATE TABLE products (
  product_id      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY
                  COMMENT 'Surrogate primary key of the product. Referenced by order_lines.product_id, product_prices.product_id, and (cross-database, no FK) PostgreSQL rma.return_lines.product_id.',
  sku             VARCHAR(64)   NOT NULL
                  COMMENT 'Stock keeping unit; unique business identifier of the product, e.g. TSHIRT-BLK-M.',
  name            VARCHAR(255)  NOT NULL
                  COMMENT 'Current product display name. For the name at time of sale use order_lines.product_name.',
  description     TEXT          NULL
                  COMMENT 'Long marketing description (free text).',
  category_id     INT UNSIGNED  NULL
                  COMMENT 'FK -> categories.category_id. NULL = uncategorized.',
  brand           VARCHAR(100)  NULL
                  COMMENT 'Brand or manufacturer name.',
  weight_grams    INT UNSIGNED  NULL
                  COMMENT 'Shipping weight of one unit in grams.',
  status          ENUM('draft','active','discontinued') NOT NULL DEFAULT 'active'
                  COMMENT 'draft = not yet visible; active = on sale; discontinued = no longer sold but kept for order history.',
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                  COMMENT 'UTC time the product was created (launch date proxy).',
  updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                  COMMENT 'UTC time of the last change to this row.',
  UNIQUE KEY uq_products_sku (sku),
  KEY idx_products_category (category_id),
  KEY idx_products_status (status),
  CONSTRAINT fk_prod_category FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE SET NULL
) ENGINE=InnoDB
  COMMENT='Product catalog, one row per SKU. Descriptive data only; prices are in product_prices (join on product_id, effective_to IS NULL for the current price). Grain: one row per sellable product.';

-- =====================================================================
-- PRODUCT_PRICES
-- =====================================================================
CREATE TABLE product_prices (
  product_price_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY
                   COMMENT 'Surrogate primary key of the price record. Referenced by order_lines.product_price_id.',
  product_id       BIGINT UNSIGNED NOT NULL
                   COMMENT 'FK -> products.product_id.',
  list_price       DECIMAL(12,2) NOT NULL
                   COMMENT 'Regular selling price per unit, before discounts and tax (a.k.a. MSRP / compare-at price).',
  sale_price       DECIMAL(12,2) NULL
                   COMMENT 'Promotional price per unit during this period. NULL = no sale; customer pays list_price. Must be <= list_price. Effective price = COALESCE(sale_price, list_price).',
  currency         CHAR(3)       NOT NULL DEFAULT 'USD'
                   COMMENT 'ISO 4217 currency of the price amounts.',
  change_reason    ENUM('launch','regular_change','promotion','clearance','correction') NOT NULL DEFAULT 'regular_change'
                   COMMENT 'Why this price row was created. launch = first price; promotion = temporary sale; clearance = markdown to sell out; correction = fix of a wrong price.',
  effective_from   DATETIME      NOT NULL
                   COMMENT 'UTC time (inclusive) from which this price applies.',
  effective_to     DATETIME      NULL
                   COMMENT 'UTC time (exclusive) at which this price stops applying. NULL = current price, still in effect.',
  created_by       VARCHAR(100)  NULL
                   COMMENT 'User or system that set the price (for audit).',
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                   COMMENT 'UTC time this price record was entered.',
  CONSTRAINT fk_price_product FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
  KEY idx_price_product_dates (product_id, effective_from, effective_to),
  CONSTRAINT chk_price_nonneg CHECK (list_price >= 0 AND (sale_price IS NULL OR sale_price >= 0)),
  CONSTRAINT chk_price_sale_le_list CHECK (sale_price IS NULL OR sale_price <= list_price),
  CONSTRAINT chk_price_dates CHECK (effective_to IS NULL OR effective_to > effective_from)
) ENGINE=InnoDB
  COMMENT='Effective-dated (slowly changing, type 2) selling-price history per product. Ranges are half-open [effective_from, effective_to), must not overlap for one product, and exactly one row per product has effective_to NULL (the current price). Used to fill order_lines.unit_price and unit_list_price at checkout and for price-change analysis. Grain: one row per product per price period.';

-- =====================================================================
-- ORDERS
-- =====================================================================
CREATE TABLE orders (
  order_id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY
                      COMMENT 'Surrogate primary key of the order. Referenced by order_lines.order_id and (cross-database, no FK) PostgreSQL rma.returns.order_id.',
  order_number        VARCHAR(32)   NOT NULL
                      COMMENT 'Customer-facing unique order reference, e.g. ORD-2026-000123. Also copied to PostgreSQL rma.returns.order_number.',
  user_id             BIGINT UNSIGNED NOT NULL
                      COMMENT 'FK -> users.user_id. Customer who placed the order.',
  status              ENUM('pending','paid','processing','shipped','delivered',
                           'cancelled','partially_returned','returned') NOT NULL DEFAULT 'pending'
                      COMMENT 'Lifecycle: pending (awaiting payment) -> paid -> processing (picking/packing) -> shipped -> delivered. cancelled = voided before shipping. partially_returned / returned are set by the returns service (PostgreSQL) when some or all units came back. Exclude pending and cancelled when measuring sales.',
  channel             ENUM('web','mobile_app','marketplace','phone','pos') NOT NULL DEFAULT 'web'
                      COMMENT 'Sales channel where the order was placed.',
  currency            CHAR(3)       NOT NULL DEFAULT 'USD'
                      COMMENT 'ISO 4217 currency of all amounts on this order and its lines.',
  subtotal_amount     DECIMAL(12,2) NOT NULL DEFAULT 0
                      COMMENT 'Sum of order_lines.line_total (after line discounts, before order discount, shipping and tax).',
  discount_amount     DECIMAL(12,2) NOT NULL DEFAULT 0
                      COMMENT 'Order-level discount (e.g. basket coupon), positive number, in addition to line discounts.',
  shipping_amount     DECIMAL(12,2) NOT NULL DEFAULT 0
                      COMMENT 'Shipping fee charged to the customer.',
  tax_amount          DECIMAL(12,2) NOT NULL DEFAULT 0
                      COMMENT 'Total sales tax/VAT charged on the order.',
  total_amount        DECIMAL(12,2) NOT NULL DEFAULT 0
                      COMMENT 'Amount charged to the customer = subtotal_amount - discount_amount + shipping_amount + tax_amount. Not reduced by refunds.',
  coupon_code         VARCHAR(50)   NULL
                      COMMENT 'Promotion code applied at checkout, if any.',
  ship_name           VARCHAR(200)  NULL
                      COMMENT 'Recipient name, copied at checkout (snapshot).',
  ship_line1          VARCHAR(255)  NULL
                      COMMENT 'Ship-to street line 1 (snapshot).',
  ship_line2          VARCHAR(255)  NULL
                      COMMENT 'Ship-to street line 2 (snapshot).',
  ship_city           VARCHAR(100)  NULL
                      COMMENT 'Ship-to city (snapshot). Use for geographic sales analysis.',
  ship_state_region   VARCHAR(100)  NULL
                      COMMENT 'Ship-to state/region (snapshot).',
  ship_postal_code    VARCHAR(20)   NULL
                      COMMENT 'Ship-to postal code (snapshot).',
  ship_country_code   CHAR(2)       NULL
                      COMMENT 'Ship-to ISO 3166-1 alpha-2 country (snapshot).',
  placed_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                      COMMENT 'UTC time the order was placed. THE date to use for sales reporting (daily/monthly revenue).',
  paid_at             DATETIME      NULL
                      COMMENT 'UTC time payment was captured. NULL if not paid.',
  shipped_at          DATETIME      NULL
                      COMMENT 'UTC time the order (first shipment) left the warehouse.',
  delivered_at        DATETIME      NULL
                      COMMENT 'UTC time the carrier confirmed delivery. delivered_at - shipped_at = transit time. Compare with PostgreSQL rma.returns.requested_at for days-to-return.',
  cancelled_at        DATETIME      NULL
                      COMMENT 'UTC time the order was cancelled. NULL if not cancelled.',
  updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                      COMMENT 'UTC time of the last change to this row.',
  UNIQUE KEY uq_orders_number (order_number),
  KEY idx_orders_user_date (user_id, placed_at),
  KEY idx_orders_status_date (status, placed_at),
  KEY idx_orders_placed (placed_at),
  CONSTRAINT fk_order_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
  CONSTRAINT chk_order_amounts CHECK (subtotal_amount >= 0 AND discount_amount >= 0
                                      AND shipping_amount >= 0 AND tax_amount >= 0
                                      AND total_amount >= 0)
) ENGINE=InnoDB
  COMMENT='Order header. One row per customer checkout. Money totals here are order-level and gross (refunds are in PostgreSQL rma.returns); item-level detail is in order_lines. Grain: one row per order.';

-- =====================================================================
-- ORDER_LINES
-- =====================================================================
CREATE TABLE order_lines (
  order_line_id    BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY
                   COMMENT 'Surrogate primary key of the order line. Referenced (cross-database, no FK) by PostgreSQL rma.return_lines.order_line_id; the key for merging sales with returns.',
  order_id         BIGINT UNSIGNED NOT NULL
                   COMMENT 'FK -> orders.order_id. Order this line belongs to.',
  line_number      SMALLINT UNSIGNED NOT NULL
                   COMMENT 'Position of the line within its order (1, 2, 3 ...). Unique per order.',
  product_id       BIGINT UNSIGNED NOT NULL
                   COMMENT 'FK -> products.product_id. Product sold.',
  product_price_id BIGINT UNSIGNED NULL
                   COMMENT 'FK -> product_prices.product_price_id. Price record in effect at checkout (audit link). NULL if the price was set manually.',
  sku              VARCHAR(64)   NOT NULL
                   COMMENT 'SKU at time of sale (snapshot of products.sku).',
  product_name     VARCHAR(255)  NOT NULL
                   COMMENT 'Product name at time of sale (snapshot of products.name).',
  quantity         INT UNSIGNED  NOT NULL
                   COMMENT 'Units ordered on this line. Always > 0. Denominator for unit return rate.',
  unit_list_price  DECIMAL(12,2) NOT NULL
                   COMMENT 'List (regular) price per unit at time of sale (snapshot of product_prices.list_price). Use with unit_price to measure markdowns.',
  unit_price       DECIMAL(12,2) NOT NULL
                   COMMENT 'Price per unit actually charged, before line discount and tax (snapshot; = COALESCE(sale_price, list_price) at checkout unless overridden). Use for all historical revenue.',
  discount_amount  DECIMAL(12,2) NOT NULL DEFAULT 0
                   COMMENT 'Total extra discount on this line (not per unit), e.g. coupon share; positive number.',
  tax_amount       DECIMAL(12,2) NOT NULL DEFAULT 0
                   COMMENT 'Tax charged on this line.',
  line_total       DECIMAL(12,2) AS (quantity * unit_price - discount_amount) STORED
                   COMMENT 'Generated column = quantity * unit_price - discount_amount. Gross line revenue excluding tax. Sum per order = orders.subtotal_amount.',
  status           ENUM('open','shipped','cancelled','returned','partially_returned') NOT NULL DEFAULT 'open'
                   COMMENT 'Line state. open = not yet shipped; shipped; cancelled = removed before shipping (exclude from sales); returned / partially_returned are set by the returns service (units and refunds are in PostgreSQL).',
  UNIQUE KEY uq_line_order_num (order_id, line_number),
  KEY idx_line_product (product_id),
  KEY idx_line_price (product_price_id),
  CONSTRAINT fk_line_order   FOREIGN KEY (order_id)         REFERENCES orders(order_id)                 ON DELETE CASCADE,
  CONSTRAINT fk_line_product FOREIGN KEY (product_id)       REFERENCES products(product_id)             ON DELETE RESTRICT,
  CONSTRAINT fk_line_price   FOREIGN KEY (product_price_id) REFERENCES product_prices(product_price_id) ON DELETE SET NULL,
  CONSTRAINT chk_line_qty  CHECK (quantity > 0),
  CONSTRAINT chk_line_vals CHECK (unit_list_price >= 0 AND unit_price >= 0 AND discount_amount >= 0 AND tax_amount >= 0)
) ENGINE=InnoDB
  COMMENT='Order detail (fact table for sales). One row per product per order with price snapshots. Bridge between orders and products. Grain: one row per order per product line.';

-- =====================================================================
-- VIEW: current price per product
-- =====================================================================
CREATE OR REPLACE VIEW v_product_current_price AS
SELECT
  p.product_id,
  p.sku,
  p.name,
  p.category_id,
  p.status,
  pp.list_price,
  pp.sale_price,
  COALESCE(pp.sale_price, pp.list_price) AS effective_price,
  pp.currency,
  pp.effective_from                      AS price_since
FROM products p
LEFT JOIN product_prices pp
       ON pp.product_id = p.product_id
      AND pp.effective_to IS NULL;

-- =====================================================================
-- VIEW: line-level gross sales (returns NOT included; they are in PostgreSQL)
-- =====================================================================
-- Excludes pending/cancelled orders and cancelled lines. To get net
-- revenue, merge on order_line_id with PostgreSQL
-- rma.v_returned_by_order_line and subtract `refunded`.
CREATE OR REPLACE VIEW v_order_line_sales AS
SELECT
  ol.order_line_id,
  o.order_id,
  o.order_number,
  o.user_id,
  o.placed_at,
  o.channel,
  o.status                                         AS order_status,
  ol.product_id,
  p.category_id,
  ol.sku,
  ol.product_name,
  ol.quantity                                      AS sold_qty,
  ol.unit_list_price,
  ol.unit_price,
  ol.quantity * ol.unit_list_price                 AS list_value,
  ol.line_total                                    AS gross_revenue,
  ol.quantity * ol.unit_list_price - ol.line_total AS total_markdown
FROM order_lines ol
JOIN orders o   ON o.order_id = ol.order_id
JOIN products p ON p.product_id = ol.product_id
WHERE o.status NOT IN ('pending','cancelled')
  AND ol.status <> 'cancelled';

-- =====================================================================
-- EXAMPLE QUESTIONS -> SQL  (few-shot examples for text-to-SQL, MySQL)
-- Return-related examples are in returns_postgres_schema.sql.
-- =====================================================================
-- Q1: Monthly gross revenue and order count in 2026.
--   SELECT DATE_FORMAT(placed_at, '%Y-%m') AS month,
--          COUNT(DISTINCT order_id)       AS orders,
--          SUM(gross_revenue)             AS gross_revenue
--   FROM v_order_line_sales
--   WHERE placed_at >= '2026-01-01' AND placed_at < '2027-01-01'
--   GROUP BY month ORDER BY month;
--
-- Q2: Top 10 products by gross revenue in the last 90 days.
--   SELECT sku, product_name, SUM(sold_qty) AS units, SUM(gross_revenue) AS gross_revenue
--   FROM v_order_line_sales
--   WHERE placed_at >= NOW() - INTERVAL 90 DAY
--   GROUP BY sku, product_name
--   ORDER BY gross_revenue DESC LIMIT 10;
--
-- Q3: Gross revenue by top-level category.
--   SELECT COALESCE(parent.name, c.name, 'Uncategorized') AS top_category,
--          SUM(v.gross_revenue) AS gross_revenue
--   FROM v_order_line_sales v
--   LEFT JOIN categories c      ON c.category_id = v.category_id
--   LEFT JOIN categories parent ON parent.category_id = c.parent_id
--   GROUP BY top_category ORDER BY gross_revenue DESC;
--
-- Q4: Customer lifetime gross revenue and order count.
--   SELECT u.user_id, u.email, COUNT(DISTINCT v.order_id) AS orders,
--          SUM(v.gross_revenue) AS lifetime_gross_revenue
--   FROM users u
--   JOIN v_order_line_sales v ON v.user_id = u.user_id
--   GROUP BY u.user_id, u.email
--   ORDER BY lifetime_gross_revenue DESC;
--   (For NET lifetime value, subtract refunds per user_id from PostgreSQL
--    rma.returns where status IN ('refunded','closed'), merged in code.)
--
-- Q5: Current price of every active product, showing items on sale.
--   SELECT sku, name, list_price, sale_price, effective_price,
--          CASE WHEN sale_price IS NOT NULL
--               THEN ROUND(100 * (1 - sale_price / list_price), 1) END AS pct_off
--   FROM v_product_current_price
--   WHERE status = 'active'
--   ORDER BY pct_off DESC;
--
-- Q6: Price history of one SKU.
--   SELECT pp.effective_from, pp.effective_to, pp.list_price, pp.sale_price, pp.change_reason
--   FROM product_prices pp
--   JOIN products p ON p.product_id = pp.product_id
--   WHERE p.sku = 'TSHIRT-BLK-M'
--   ORDER BY pp.effective_from;
--
-- Q7: Price of each product on a given date (2026-06-01).
--   SELECT p.sku, pp.list_price, COALESCE(pp.sale_price, pp.list_price) AS effective_price
--   FROM products p
--   JOIN product_prices pp ON pp.product_id = p.product_id
--    AND pp.effective_from <= '2026-06-01'
--    AND (pp.effective_to IS NULL OR pp.effective_to > '2026-06-01');
--
-- Q8: Markdown impact by month: revenue lost to sale prices and discounts vs list.
--   SELECT DATE_FORMAT(placed_at, '%Y-%m') AS month,
--          SUM(list_value)     AS list_value,
--          SUM(gross_revenue)  AS gross_revenue,
--          SUM(total_markdown) AS markdown,
--          SUM(total_markdown) / SUM(list_value) AS markdown_pct
--   FROM v_order_line_sales
--   GROUP BY month ORDER BY month;
--
-- Q9: Items of a given order number (returns for it: query PostgreSQL
--     rma.v_return_lines_detail WHERE order_number = 'ORD-2026-000123').
--   SELECT ol.order_line_id, ol.line_number, ol.sku, ol.product_name,
--          ol.quantity, ol.unit_price, ol.line_total, ol.status
--   FROM orders o
--   JOIN order_lines ol ON ol.order_id = o.order_id
--   WHERE o.order_number = 'ORD-2026-000123'
--   ORDER BY ol.line_number;
--
-- Q10: Sales side of a unit return rate by product (merge with PostgreSQL
--      rma.v_returned_by_order_line on order_line_id, or aggregate both
--      sides by product_id and merge on product_id).
--   SELECT product_id, sku, SUM(sold_qty) AS sold_qty
--   FROM v_order_line_sales
--   WHERE placed_at >= NOW() - INTERVAL 90 DAY
--   GROUP BY product_id, sku;
-- =====================================================================
