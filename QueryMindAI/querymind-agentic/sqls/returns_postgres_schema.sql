-- =====================================================================
-- RETURNS SCHEMA  (PostgreSQL 13+)            database: returns_db
--                                             schema:   rma
-- =====================================================================
-- PURPOSE
--   Customer returns (RMAs) for the e-commerce store. This database is
--   SEPARATE from the main MySQL database `ecommerce`, which holds users,
--   products, product_prices, orders and order_lines
--   (see ecommerce_mysql_schema.sql).
--   Written to be read by humans AND by LLMs that generate SQL
--   (text-to-SQL). Every table and column has a COMMENT ON, and this
--   header documents relationships, cross-database links, business
--   rules and example queries.
--
-- SQL DIALECT: PostgreSQL. Use PostgreSQL syntax for queries on this
--   database: date_trunc(), INTERVAL '90 days', ::casts, FILTER (WHERE ...),
--   ILIKE, etc. Do NOT use MySQL functions such as DATE_FORMAT or
--   backtick quoting here.
--
-- ---------------------------------------------------------------------
-- TABLE OVERVIEW
-- ---------------------------------------------------------------------
--   rma.returns        Return header (RMA): one customer return request
--                      against one MySQL order.
--   rma.return_lines   Return detail: which MySQL order lines and how many
--                      units were returned. JOINING (bridge) table between
--                      rma.returns and MySQL ecommerce.order_lines.
--   rma.v_returned_by_order_line   View: returned units / refunds per order line.
--   rma.v_return_lines_detail      View: return lines joined to their header.
--
-- ---------------------------------------------------------------------
-- RELATIONSHIPS
-- ---------------------------------------------------------------------
--   Inside PostgreSQL (real foreign key):
--     rma.returns.return_id  1 --- N  rma.return_lines.return_id
--
--   Cross-database to MySQL `ecommerce` (LOGICAL references, NO foreign
--   key; integrity is enforced by the returns service at write time):
--     rma.returns.order_id          ~>  ecommerce.orders.order_id
--     rma.returns.order_number      ~>  ecommerce.orders.order_number
--     rma.returns.user_id           ~>  ecommerce.users.user_id
--     rma.return_lines.order_line_id ~> ecommerce.order_lines.order_line_id
--     rma.return_lines.product_id   ~>  ecommerce.products.product_id
--     rma.return_lines.sku          ~>  ecommerce.products.sku / order_lines.sku
--
--   Many-to-many: returns <-> order_lines is resolved by rma.return_lines.
--   One return can cover several order lines; one order line can be
--   returned across several returns (e.g. 1 unit now, 1 unit later).
--
-- ---------------------------------------------------------------------
-- ENTITY DIAGRAM (text)
-- ---------------------------------------------------------------------
--        MySQL `ecommerce`                 |   PostgreSQL `returns_db`.rma
--                                          |
--   users ............................. user_id ..........+
--     |                                    |                |
--   orders  ........................... order_id ... returns
--     |                                    |                |
--   order_lines ................... order_line_id ... return_lines
--     |                                    |
--   products ....................... product_id/sku ..(return_lines)
--                                          |
--   ( ..... = logical cross-database link, no FK;  | = real FK )
--
-- ---------------------------------------------------------------------
-- SNAPSHOT COLUMNS (why some MySQL data is copied here)
-- ---------------------------------------------------------------------
--   Because PostgreSQL cannot join MySQL directly, the returns service
--   copies the fields needed for most return reporting when the return
--   is created: order_number, order_placed_at, currency (on rma.returns)
--   and product_id, sku, product_name, unit_price, ordered_qty (on
--   rma.return_lines). Most return questions can therefore be answered
--   from PostgreSQL alone. Only questions that need data about orders
--   or items that were NOT returned (sold quantities, revenue, customer
--   names, categories) need MySQL.
--
-- ---------------------------------------------------------------------
-- HOW TO ANSWER QUESTIONS THAT NEED BOTH DATABASES
-- ---------------------------------------------------------------------
--   A single SQL statement CANNOT join MySQL and PostgreSQL tables
--   unless a foreign-data wrapper is configured (option B). Choose:
--
--   A) Two queries + merge in application code (default):
--      1. Query PostgreSQL, aggregated to the shared key, e.g.
--         SELECT order_line_id, returned_qty, refunded
--         FROM rma.v_returned_by_order_line;
--      2. Query MySQL for the same keys, e.g.
--         SELECT order_line_id, product_id, quantity, line_total
--         FROM order_lines WHERE order_line_id IN (...);
--      3. Merge on order_line_id (or order_id / user_id / product_id).
--      Always aggregate on each side BEFORE merging to avoid double counting.
--
--   B) Foreign tables (only if the DBA has run the optional mysql_fdw
--      setup at the bottom of this file): MySQL tables then appear in
--      PostgreSQL schema `ecom` (ecom.orders, ecom.order_lines,
--      ecom.products, ecom.users, ecom.categories) and can be joined in
--      one PostgreSQL query. Filter as much as possible; large scans
--      over the wrapper are slow.
--
--   C) Data warehouse: if both databases are replicated to a warehouse,
--      prefer querying there for large analytical joins.
--
-- ---------------------------------------------------------------------
-- BUSINESS RULES AND QUERY GUIDANCE
-- ---------------------------------------------------------------------
--   1. Return lifecycle (rma.returns.status):
--        requested -> approved -> received -> refunded -> closed
--        rejected  = denied; never refunds; exclude from return counts
--                    unless the question is about rejections.
--   2. A refund has actually been paid only when status IN ('refunded','closed')
--      AND refunded_at IS NOT NULL. 'requested'/'approved'/'received'
--      are open returns (refund pending).
--   3. Exchanges (refund_method = 'exchange') return goods but no money;
--      refund_amount is 0 for them. Count them as returned units, not as refunds.
--   4. Returned units of an order line = SUM(return_lines.quantity) over
--      non-rejected returns for that order_line_id. Must never exceed
--      ordered_qty (= MySQL order_lines.quantity).
--   5. Refund total of a return:
--        returns.refund_amount = SUM(return_lines.refund_amount)
--                                - restocking_fee + shipping_refund
--      For item-level refund analysis use return_lines.refund_amount;
--      for money actually paid back use returns.refund_amount.
--   6. Seller-fault reasons: damaged, wrong_item, not_as_described,
--      late_delivery. Buyer-driven reasons: size_fit, changed_mind.
--      'other' is unclassified.
--   7. Return rate needs SOLD quantities, which live in MySQL:
--        unit return rate = returned units (PostgreSQL) / sold units (MySQL
--        order_lines.quantity, excluding cancelled orders/lines).
--      Order return rate = orders with >= 1 non-rejected return / orders.
--      State which definition is used.
--   8. Dates: requested_at is the date for "returns per period"; refunded_at
--      is the date for "refunds paid per period". order_placed_at is the
--      date of the original sale (snapshot), useful for cohort return
--      rates without touching MySQL. All timestamps are timestamptz (UTC).
--   9. Days to return = requested_at - order delivered date. delivered_at is
--      only in MySQL (ecommerce.orders.delivered_at).
--  10. Money: amounts are in rma.returns.currency (ISO 4217). Do not add
--      amounts across currencies without conversion.
--  11. Avoid double counting: when joining returns -> return_lines, sum
--      header amounts (returns.refund_amount, restocking_fee) from
--      rma.returns alone, not after the join.
--
-- =====================================================================

-- Run as a superuser / owner of returns_db:
--   CREATE DATABASE returns_db ENCODING 'UTF8';
--   \c returns_db

CREATE SCHEMA IF NOT EXISTS rma;
COMMENT ON SCHEMA rma IS 'Returns (RMA) domain of the e-commerce platform. Links to the MySQL ecommerce database by order_id, order_line_id, user_id and product_id (logical references, no foreign keys).';

-- ---------------------------------------------------------------------
-- Shared trigger function: keep updated_at current
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION rma.set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

-- =====================================================================
-- RMA.RETURNS
-- =====================================================================
CREATE TABLE rma.returns (
  return_id        bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  rma_number       varchar(32)   NOT NULL,
  order_id         bigint        NOT NULL,
  order_number     varchar(32)   NOT NULL,
  order_placed_at  timestamptz   NULL,
  user_id          bigint        NOT NULL,
  currency         char(3)       NOT NULL DEFAULT 'USD',
  status           varchar(20)   NOT NULL DEFAULT 'requested',
  reason_code      varchar(30)   NOT NULL,
  customer_notes   text          NULL,
  refund_method    varchar(20)   NULL,
  refund_amount    numeric(12,2) NOT NULL DEFAULT 0,
  restocking_fee   numeric(12,2) NOT NULL DEFAULT 0,
  shipping_refund  numeric(12,2) NOT NULL DEFAULT 0,
  requested_at     timestamptz   NOT NULL DEFAULT now(),
  approved_at      timestamptz   NULL,
  received_at      timestamptz   NULL,
  refunded_at      timestamptz   NULL,
  closed_at        timestamptz   NULL,
  created_at       timestamptz   NOT NULL DEFAULT now(),
  updated_at       timestamptz   NOT NULL DEFAULT now(),
  CONSTRAINT uq_returns_rma UNIQUE (rma_number),
  CONSTRAINT chk_returns_status CHECK (status IN
    ('requested','approved','rejected','received','refunded','closed')),
  CONSTRAINT chk_returns_reason CHECK (reason_code IN
    ('damaged','wrong_item','not_as_described','size_fit','changed_mind','late_delivery','other')),
  CONSTRAINT chk_returns_refund_method CHECK (refund_method IS NULL OR refund_method IN
    ('original_payment','store_credit','exchange')),
  CONSTRAINT chk_returns_amounts CHECK (refund_amount >= 0 AND restocking_fee >= 0 AND shipping_refund >= 0),
  CONSTRAINT chk_returns_refunded_time CHECK (status <> 'refunded' OR refunded_at IS NOT NULL)
);

CREATE INDEX idx_returns_order        ON rma.returns (order_id);
CREATE INDEX idx_returns_order_number ON rma.returns (order_number);
CREATE INDEX idx_returns_user_date    ON rma.returns (user_id, requested_at);
CREATE INDEX idx_returns_status_date  ON rma.returns (status, requested_at);
CREATE INDEX idx_returns_refunded_at  ON rma.returns (refunded_at) WHERE refunded_at IS NOT NULL;

CREATE TRIGGER trg_returns_updated_at BEFORE UPDATE ON rma.returns
  FOR EACH ROW EXECUTE FUNCTION rma.set_updated_at();

COMMENT ON TABLE rma.returns IS
  'Return header (RMA). One row per customer return request against one MySQL order; an order can have several returns. Item detail is in rma.return_lines. Grain: one row per return request.';
COMMENT ON COLUMN rma.returns.return_id       IS 'Surrogate primary key of the return. Referenced by rma.return_lines.return_id.';
COMMENT ON COLUMN rma.returns.rma_number      IS 'Customer-facing Return Merchandise Authorization number, e.g. RMA-2026-000045. Unique. Use when the user mentions an RMA number.';
COMMENT ON COLUMN rma.returns.order_id        IS 'Logical reference to MySQL ecommerce.orders.order_id (no FK, different database). The order the goods are returned from.';
COMMENT ON COLUMN rma.returns.order_number    IS 'Snapshot of MySQL ecommerce.orders.order_number, e.g. ORD-2026-000123. Lets you find returns by order number without MySQL.';
COMMENT ON COLUMN rma.returns.order_placed_at IS 'Snapshot of MySQL ecommerce.orders.placed_at (UTC). Date of the original sale; use for cohort analysis without MySQL.';
COMMENT ON COLUMN rma.returns.user_id         IS 'Logical reference to MySQL ecommerce.users.user_id (no FK). Customer requesting the return; equals the order''s user_id.';
COMMENT ON COLUMN rma.returns.currency        IS 'ISO 4217 currency of all amounts on this return; same as the MySQL order currency.';
COMMENT ON COLUMN rma.returns.status          IS 'Lifecycle: requested -> approved (label issued) -> received (goods back at warehouse) -> refunded (money returned) -> closed. rejected = denied, no refund. Count paid refunds only for refunded/closed.';
COMMENT ON COLUMN rma.returns.reason_code     IS 'Primary reason given by the customer: damaged, wrong_item, not_as_described, late_delivery (seller-fault); size_fit, changed_mind (buyer-driven); other.';
COMMENT ON COLUMN rma.returns.customer_notes  IS 'Free-text explanation from the customer. Use ILIKE or full-text search for keyword questions.';
COMMENT ON COLUMN rma.returns.refund_method   IS 'How the customer is compensated: original_payment, store_credit, or exchange (replacement item, no money refunded). NULL until decided.';
COMMENT ON COLUMN rma.returns.refund_amount   IS 'Total money refunded for this return = SUM(return_lines.refund_amount) - restocking_fee + shipping_refund. 0 for exchanges and rejected returns.';
COMMENT ON COLUMN rma.returns.restocking_fee  IS 'Fee withheld from the refund, positive number.';
COMMENT ON COLUMN rma.returns.shipping_refund IS 'Original shipping fee refunded to the customer (e.g. for seller-fault returns).';
COMMENT ON COLUMN rma.returns.requested_at    IS 'UTC time the return was requested. THE date for "returns per period".';
COMMENT ON COLUMN rma.returns.approved_at     IS 'UTC time the return was approved (or rejected). NULL while requested.';
COMMENT ON COLUMN rma.returns.received_at     IS 'UTC time the returned goods arrived at the warehouse. received_at - requested_at = return transit time.';
COMMENT ON COLUMN rma.returns.refunded_at     IS 'UTC time the refund was issued. THE date for "refunds paid per period". refunded_at - received_at = refund processing time.';
COMMENT ON COLUMN rma.returns.closed_at       IS 'UTC time the return case was closed.';
COMMENT ON COLUMN rma.returns.created_at      IS 'UTC time the row was inserted.';
COMMENT ON COLUMN rma.returns.updated_at      IS 'UTC time of the last change to the row (maintained by trigger).';

-- =====================================================================
-- RMA.RETURN_LINES  (joining / bridge table: returns <-> MySQL order_lines)
-- =====================================================================
CREATE TABLE rma.return_lines (
  return_line_id   bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  return_id        bigint        NOT NULL,
  order_line_id    bigint        NOT NULL,
  product_id       bigint        NOT NULL,
  sku              varchar(64)   NOT NULL,
  product_name     varchar(255)  NOT NULL,
  unit_price       numeric(12,2) NOT NULL,
  ordered_qty      integer       NOT NULL,
  quantity         integer       NOT NULL,
  item_condition   varchar(20)   NULL,
  restock          boolean       NOT NULL DEFAULT true,
  refund_amount    numeric(12,2) NOT NULL DEFAULT 0,
  created_at       timestamptz   NOT NULL DEFAULT now(),
  CONSTRAINT fk_rl_return FOREIGN KEY (return_id) REFERENCES rma.returns (return_id) ON DELETE CASCADE,
  CONSTRAINT uq_return_line UNIQUE (return_id, order_line_id),
  CONSTRAINT chk_rl_qty CHECK (quantity > 0 AND ordered_qty > 0 AND quantity <= ordered_qty),
  CONSTRAINT chk_rl_condition CHECK (item_condition IS NULL OR item_condition IN
    ('new','opened','damaged','defective')),
  CONSTRAINT chk_rl_amounts CHECK (unit_price >= 0 AND refund_amount >= 0)
);

CREATE INDEX idx_rl_order_line ON rma.return_lines (order_line_id);
CREATE INDEX idx_rl_product    ON rma.return_lines (product_id);
CREATE INDEX idx_rl_sku        ON rma.return_lines (sku);

COMMENT ON TABLE rma.return_lines IS
  'Joining (bridge) table resolving the many-to-many between rma.returns and MySQL ecommerce.order_lines: which units of which order line were returned in which return. Carries product and price snapshots so item-level return reporting needs no MySQL join. Grain: one row per return per order line.';
COMMENT ON COLUMN rma.return_lines.return_line_id IS 'Surrogate primary key of the return line.';
COMMENT ON COLUMN rma.return_lines.return_id      IS 'FK -> rma.returns.return_id. Return request this line belongs to.';
COMMENT ON COLUMN rma.return_lines.order_line_id  IS 'Logical reference to MySQL ecommerce.order_lines.order_line_id (no FK). The original order line being returned; it belongs to the order in rma.returns.order_id. Key for merging with MySQL sales data.';
COMMENT ON COLUMN rma.return_lines.product_id     IS 'Snapshot of MySQL ecommerce.order_lines.product_id. Logical reference to ecommerce.products.product_id; use to get category/brand from MySQL.';
COMMENT ON COLUMN rma.return_lines.sku            IS 'Snapshot of the SKU as sold (ecommerce.order_lines.sku).';
COMMENT ON COLUMN rma.return_lines.product_name   IS 'Snapshot of the product name as sold (ecommerce.order_lines.product_name).';
COMMENT ON COLUMN rma.return_lines.unit_price     IS 'Snapshot of ecommerce.order_lines.unit_price: price per unit the customer paid. quantity * unit_price = returned merchandise value.';
COMMENT ON COLUMN rma.return_lines.ordered_qty    IS 'Snapshot of ecommerce.order_lines.quantity: units originally ordered on that line. Upper bound for total returned units.';
COMMENT ON COLUMN rma.return_lines.quantity       IS 'Units returned on this line in this return. SUM over all non-rejected returns of an order line must not exceed ordered_qty.';
COMMENT ON COLUMN rma.return_lines.item_condition IS 'Condition on inspection at the warehouse: new, opened, damaged, defective. NULL until received.';
COMMENT ON COLUMN rma.return_lines.restock        IS 'true = unit goes back to sellable stock; false = written off (damaged/defective).';
COMMENT ON COLUMN rma.return_lines.refund_amount  IS 'Money refunded for these units, usually quantity * unit_price minus prorated line discount. 0 for exchanges.';
COMMENT ON COLUMN rma.return_lines.created_at     IS 'UTC time the row was inserted.';

-- =====================================================================
-- VIEW: returned units and refunds per MySQL order line
-- =====================================================================
-- Main bridge for merging with MySQL sales data on order_line_id.
-- Excludes rejected returns.
CREATE OR REPLACE VIEW rma.v_returned_by_order_line AS
SELECT
  rl.order_line_id,
  r.order_id,
  rl.product_id,
  rl.sku,
  max(rl.ordered_qty)                                              AS ordered_qty,
  sum(rl.quantity)                                                 AS returned_qty,
  sum(rl.quantity) FILTER (WHERE rl.restock)                       AS restocked_qty,
  sum(rl.refund_amount)                                            AS refund_requested,
  sum(rl.refund_amount) FILTER (WHERE r.status IN ('refunded','closed')) AS refunded,
  min(r.requested_at)                                              AS first_return_at,
  count(DISTINCT r.return_id)                                      AS return_count
FROM rma.return_lines rl
JOIN rma.returns r ON r.return_id = rl.return_id
WHERE r.status <> 'rejected'
GROUP BY rl.order_line_id, r.order_id, rl.product_id, rl.sku;

COMMENT ON VIEW rma.v_returned_by_order_line IS
  'One row per MySQL order_line_id that has at least one non-rejected return: returned/restocked units and refund amounts (requested vs actually paid). Merge with MySQL ecommerce.order_lines on order_line_id to compute return rates and net revenue.';

-- =====================================================================
-- VIEW: return lines with header data
-- =====================================================================
CREATE OR REPLACE VIEW rma.v_return_lines_detail AS
SELECT
  r.return_id, r.rma_number, r.order_id, r.order_number, r.order_placed_at,
  r.user_id, r.status, r.reason_code, r.refund_method, r.currency,
  r.requested_at, r.received_at, r.refunded_at,
  rl.return_line_id, rl.order_line_id, rl.product_id, rl.sku, rl.product_name,
  rl.unit_price, rl.ordered_qty, rl.quantity AS returned_qty,
  rl.quantity * rl.unit_price AS returned_value,
  rl.item_condition, rl.restock, rl.refund_amount AS line_refund_amount
FROM rma.returns r
JOIN rma.return_lines rl ON rl.return_id = r.return_id;

COMMENT ON VIEW rma.v_return_lines_detail IS
  'Flat view: one row per return line with its header fields. Includes rejected returns; filter on status as needed. Do not sum header amounts (refund_amount, restocking_fee) from this view; use rma.returns for those.';

-- =====================================================================
-- OPTIONAL: query MySQL tables from PostgreSQL (mysql_fdw)
-- =====================================================================
-- Uncomment and adjust if cross-database joins in one SQL statement are
-- needed (see "HOW TO ANSWER QUESTIONS THAT NEED BOTH DATABASES", option B).
-- Requires the mysql_fdw extension installed on the PostgreSQL server.
--
-- CREATE EXTENSION IF NOT EXISTS mysql_fdw;
-- CREATE SERVER ecommerce_mysql FOREIGN DATA WRAPPER mysql_fdw
--   OPTIONS (host 'mysql.internal', port '3306');
-- CREATE USER MAPPING FOR CURRENT_USER SERVER ecommerce_mysql
--   OPTIONS (username 'readonly_user', password '********');
-- CREATE SCHEMA IF NOT EXISTS ecom;
-- IMPORT FOREIGN SCHEMA ecommerce
--   LIMIT TO (users, categories, products, product_prices, orders, order_lines)
--   FROM SERVER ecommerce_mysql INTO ecom;
--
-- After this, MySQL tables are readable as ecom.orders, ecom.order_lines, etc.

-- =====================================================================
-- EXAMPLE QUESTIONS -> SQL  (few-shot examples for text-to-SQL)
-- =====================================================================
-- ---- PostgreSQL only -------------------------------------------------
-- Q1: Returns and refunds paid per month in 2026.
--   SELECT date_trunc('month', requested_at)::date AS month,
--          count(*)                                AS returns,
--          sum(refund_amount) FILTER (WHERE status IN ('refunded','closed')) AS refunded
--   FROM rma.returns
--   WHERE status <> 'rejected'
--     AND requested_at >= '2026-01-01' AND requested_at < '2027-01-01'
--   GROUP BY 1 ORDER BY 1;
--
-- Q2: Most common return reasons with share of all returns.
--   SELECT reason_code, count(*) AS returns,
--          round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
--   FROM rma.returns
--   WHERE status <> 'rejected'
--   GROUP BY reason_code ORDER BY returns DESC;
--
-- Q3: Top 10 most returned SKUs (units) in the last 90 days.
--   SELECT sku, product_name, sum(returned_qty) AS units_returned,
--          sum(returned_value) AS value_returned
--   FROM rma.v_return_lines_detail
--   WHERE status <> 'rejected' AND requested_at >= now() - INTERVAL '90 days'
--   GROUP BY sku, product_name
--   ORDER BY units_returned DESC LIMIT 10;
--
-- Q4: Open returns waiting for refund, oldest first.
--   SELECT rma_number, order_number, status, requested_at, received_at,
--          now() - requested_at AS age
--   FROM rma.returns
--   WHERE status IN ('requested','approved','received')
--   ORDER BY requested_at;
--
-- Q5: Average days from goods received to refund, by month.
--   SELECT date_trunc('month', refunded_at)::date AS month,
--          avg(extract(epoch FROM refunded_at - received_at) / 86400) AS avg_days
--   FROM rma.returns
--   WHERE refunded_at IS NOT NULL AND received_at IS NOT NULL
--   GROUP BY 1 ORDER BY 1;
--
-- Q6: Write-offs: units not restocked and their value, by condition.
--   SELECT item_condition, sum(returned_qty) AS units, sum(returned_value) AS value
--   FROM rma.v_return_lines_detail
--   WHERE NOT restock AND status <> 'rejected'
--   GROUP BY item_condition;
--
-- Q7: All returns for an order number.
--   SELECT rma_number, status, reason_code, sku, returned_qty, line_refund_amount
--   FROM rma.v_return_lines_detail
--   WHERE order_number = 'ORD-2026-000123'
--   ORDER BY requested_at, sku;
--
-- ---- Needs MySQL too (option A: two queries + merge) -----------------
-- Q8: Unit return rate by category, last 90 days.
--   PostgreSQL:
--     SELECT order_line_id, returned_qty FROM rma.v_returned_by_order_line;
--   MySQL (ecommerce):
--     SELECT ol.order_line_id, ol.quantity AS sold_qty,
--            COALESCE(c.name, 'Uncategorized') AS category
--     FROM order_lines ol
--     JOIN orders o ON o.order_id = ol.order_id
--     JOIN products p ON p.product_id = ol.product_id
--     LEFT JOIN categories c ON c.category_id = p.category_id
--     WHERE o.status NOT IN ('pending','cancelled') AND ol.status <> 'cancelled'
--       AND o.placed_at >= NOW() - INTERVAL 90 DAY;
--   Merge: LEFT JOIN MySQL rows to PostgreSQL rows on order_line_id
--   (missing = 0 returned), then per category:
--   SUM(returned_qty) / SUM(sold_qty).
--
-- Q9: Same as Q8 in ONE query (option B, only if mysql_fdw is set up).
--   SELECT COALESCE(c.name, 'Uncategorized') AS category,
--          sum(coalesce(v.returned_qty, 0))::numeric / sum(ol.quantity) AS unit_return_rate
--   FROM ecom.order_lines ol
--   JOIN ecom.orders o ON o.order_id = ol.order_id
--   JOIN ecom.products p ON p.product_id = ol.product_id
--   LEFT JOIN ecom.categories c ON c.category_id = p.category_id
--   LEFT JOIN rma.v_returned_by_order_line v ON v.order_line_id = ol.order_line_id
--   WHERE o.status NOT IN ('pending','cancelled') AND ol.status <> 'cancelled'
--     AND o.placed_at >= now() - INTERVAL '90 days'
--   GROUP BY 1 ORDER BY 2 DESC;
--
-- Q10: Customers with the most refunds, with their email (needs MySQL users).
--   PostgreSQL:
--     SELECT user_id, count(*) AS returns, sum(refund_amount) AS refunded
--     FROM rma.returns WHERE status IN ('refunded','closed')
--     GROUP BY user_id ORDER BY refunded DESC LIMIT 20;
--   MySQL:
--     SELECT user_id, email, first_name, last_name FROM users WHERE user_id IN (...);
--   Merge on user_id.
-- =====================================================================
